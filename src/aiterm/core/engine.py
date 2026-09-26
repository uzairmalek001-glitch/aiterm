"""Diagnostic engine: incremental analysis, caching, duplicate suppression, cooldowns."""
from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List

from aiterm.analyzers import python as _py
from aiterm.analyzers.base import get_analyzer, rel
from aiterm.core.config import Config
from aiterm.core.classifier import classify
from aiterm.core.models import Diagnostic
from aiterm.terminal.output_parser import parse_output

log = logging.getLogger("aiterm")


class DiagnosticEngine:
    def __init__(self, root: Path, cfg: Config):
        self.root, self.cfg = Path(root).resolve(), cfg
        _py.PythonAnalyzer.use_ruff = cfg.use_linters
        self.current: Dict[str, Dict[str, Diagnostic]] = {}   # file -> fingerprint -> diag
        self._notified: Dict[str, float] = {}                  # fingerprint -> last notify time
        self._cache: "OrderedDict[tuple, List[Diagnostic]]" = OrderedDict()
        self.analyses_run = 0                                  # analyzer invocations (cache misses)

    # ---------- deterministic file analysis ----------
    def analyze_file(self, path: Path) -> List[Diagnostic]:
        path = Path(path)
        if not path.is_absolute():
            path = self.root / path
        r = rel(path, self.root)
        an = get_analyzer(path)
        if an is None or an.name not in self.cfg.languages:
            return []
        try:
            data = path.read_bytes()
        except OSError:
            self.current.pop(r, None)  # deleted: its problems are gone
            return []
        key = (str(path), hashlib.sha1(data).hexdigest())
        if key in self._cache:
            self._cache.move_to_end(key)
            diags = self._cache[key]
        else:
            try:
                diags = an.analyze(path, self.root)
                self.analyses_run += 1
            except Exception as e:  # an analyzer bug must not stop monitoring
                log.warning("analyzer %s failed on %s: %s", an.name, r, e)
                diags = []
            diags = [d for d in diags if not any(s in d.message for s in self.cfg.ignore_messages)]
            self._cache[key] = diags
            if len(self._cache) > 512:
                self._cache.popitem(last=False)
        self.current.pop(r, None)
        for d in diags:
            self.current.setdefault(d.file, {})[d.fingerprint] = d
        return diags

    def analyze_paths(self, paths: Iterable[Path]) -> List[Diagnostic]:
        out: List[Diagnostic] = []
        for p in paths:
            out += self.analyze_file(p)
        return out

    # ---------- runtime / terminal output ----------
    def ingest_output(self, text: str, source: str = "terminal") -> List[Diagnostic]:
        diags = [d for d in parse_output(text, self.root, source)
                 if not any(s in d.message for s in self.cfg.ignore_messages)]
        for d in diags:
            self.current.setdefault(d.file, {})[d.fingerprint] = d
        return diags

    @staticmethod
    def _extract_location(text: str):
        """Extract a source-file and line number from command output."""
        import re

        # Format 1: file.py:10
        direct = re.compile(
            r'(?<!https://)(?<!http://)'
            r'(?P<path>(?:[A-Za-z]:[\\/]|/|\.\.?/)?'
            r'[A-Za-z0-9_.-]+(?:[\\/][A-Za-z0-9_.-]+)*'
            r'\.[A-Za-z][A-Za-z0-9_-]*)'
            r':(?P<line>\d+)(?!\d)'
        )

        for match in direct.finditer(text):
            token_start = text.rfind(" ", 0, match.start()) + 1
            token = text[token_start:match.end()]
            if "://" not in token:
                return match.group("path"), int(match.group("line"))

        # Format 2: file.py: ... at line 10
        contextual = re.compile(
            r'(?P<path>(?:[A-Za-z]:[\\/]|/|\.\.?/)?'
            r'[A-Za-z0-9_.-]+(?:[\\/][A-Za-z0-9_.-]+)*'
            r'\.[A-Za-z][A-Za-z0-9_-]*)'
            r':[^\n]{0,200}?\bline\s+(?P<line>\d+)\b',
            re.IGNORECASE,
        )

        for match in contextual.finditer(text):
            return match.group("path"), int(match.group("line"))

        return None, 0

    def ingest_command_result(
        self,
        text: str,
        exit_code: int,
        command: str = "<command>",
        source: str = "terminal",
    ) -> List[Diagnostic]:
        """Parse command output and create a fallback diagnostic on failure."""
        diags = self.ingest_output(text, source)

        if exit_code != 0 and not diags:
            location, line = self._extract_location(text)

            d = Diagnostic(
                file=location or command,
                line=line,
                column=0,
                severity="error",
                category="UNKNOWN",
                message=f"Command failed with exit code {exit_code}: {command}",
                source="command-exit",
                raw=text[-2000:],
            )

            d.category = classify(d)

            self.current.setdefault(d.file, {})[d.fingerprint] = d
            diags.append(d)

        return diags

    # ---------- suppression ----------
    def fresh(self, diags: Iterable[Diagnostic], now: float = None) -> List[Diagnostic]:
        """Drop problems already announced (until resolved or the cooldown lapses)."""
        now = time.monotonic() if now is None else now
        out = []
        for d in diags:
            last = self._notified.get(d.fingerprint)
            if last is not None and now - last < self.cfg.cooldown_seconds:
                continue
            self._notified[d.fingerprint] = now
            out.append(d)
        return out

    def forget_resolved(self) -> None:
        live = {fp for per in self.current.values() for fp in per}
        for fp in [f for f in self._notified if f not in live]:
            del self._notified[fp]

    def all_current(self) -> List[Diagnostic]:
        return sorted((d for per in self.current.values() for d in per.values()),
                      key=lambda d: (-d.rank, d.file, d.line))
