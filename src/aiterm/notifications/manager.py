"""Non-intrusive notifications: filtered, batched, severity-aware; terminal / desktop / file sinks."""
from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import List, Optional, TextIO

from aiterm.ai.base import AIResult
from aiterm.core.config import NotifyConfig
from aiterm.core.models import Diagnostic
from aiterm.security.redact import redact

ICON = {"info": "ℹ", "warning": "⚠", "error": "⚠", "critical": "✖"}


def render_box(d: Diagnostic, ai: Optional[AIResult] = None, width: int = 66) -> str:
    inner = width - 4
    rows: List[str] = [f"{ICON.get(d.severity, '⚠')} AI Code Assistant  [{d.severity.upper()}]", ""]
    label = d.category.replace("_", " ").capitalize()
    rows += [f"{label} detected", ""]
    rows.append(f"File: {d.file}")
    if d.line:
        rows.append(f"Line: {d.line}")
    rows.append("")
    rows += textwrap.wrap(redact(d.message), inner) or [""]
    if d.hint:
        rows += ["", "Why:"] + textwrap.wrap(d.hint, inner)
    if d.fix_line:
        rows += ["", "Suggested fix (deterministic):", redact(d.fix_line.strip())]
    if ai:
        rows += ["", f"AI analysis (inference, confidence {ai.confidence:.0%}):"]
        for t in (ai.cause, ai.explanation):
            rows += textwrap.wrap(t, inner)
        if ai.suggested_fix:
            rows += ["Suggested:"] + textwrap.wrap(ai.suggested_fix, inner)
        if ai.requires_manual_review:
            rows.append("(manual review recommended)")
    rows += ["", "[Explain] [Fix] [Dismiss]", f"aiterm explain {d.id} | aiterm fix {d.id}"]
    body = "\n".join(f"│ {r[:inner].ljust(inner)} │" for r in rows)
    return f"┌{'─' * (width - 2)}┐\n{body}\n└{'─' * (width - 2)}┘"


class Sink:
    def send(self, d: Diagnostic, ai: Optional[AIResult]) -> None: ...
    def summary(self, text: str) -> None: ...


class TerminalSink(Sink):
    def __init__(self, stream: Optional[TextIO] = None):
        self.stream = stream or sys.stderr

    def send(self, d, ai):
        self.stream.write("\n" + render_box(d, ai) + "\n")
        self.stream.flush()

    def summary(self, text):
        self.stream.write(f"\n[aiterm] {text}\n")
        self.stream.flush()


class DesktopSink(Sink):
    """notify-send on Linux; silently inactive elsewhere."""

    def __init__(self):
        self.exe = shutil.which("notify-send")

    def send(self, d, ai):
        if not self.exe:
            return
        urgency = {"info": "low", "warning": "normal"}.get(d.severity, "critical")
        body = redact(f"{d.file}:{d.line}\n{d.message}" + (f"\n{d.fix_line.strip()}" if d.fix_line else ""))
        try:
            subprocess.Popen([self.exe, "-u", urgency, "-a", "aiterm", f"aiterm: {d.category}", body],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


class FileSink(Sink):
    def __init__(self, path: Path):
        self.path = Path(path)

    def send(self, d, ai):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                msg = redact(d.message).replace("\n", " ")   # logs never contain secrets or raw traces
                f.write(f"{d.timestamp} {d.severity.upper()} {d.file}:{d.line} [{d.id}] {msg}\n")
        except OSError:
            pass


class ListSink(Sink):
    def __init__(self):
        self.sent, self.summaries = [], []

    def send(self, d, ai):
        self.sent.append((d, ai))

    def summary(self, text):
        self.summaries.append(text)


class NotificationManager:
    def __init__(self, cfg: NotifyConfig, sinks: List[Sink]):
        self.cfg, self.sinks = cfg, sinks

    def wanted(self, d: Diagnostic) -> bool:
        if d.category == "PERFORMANCE_WARNING":
            return self.cfg.performance
        if d.severity in ("error", "critical"):
            return self.cfg.errors
        if d.severity == "warning":
            return self.cfg.warnings
        return self.cfg.style

    def notify(self, items: List[tuple]) -> int:
        """items = [(Diagnostic, AIResult|None)]. Most severe first; overflow collapses into one line."""
        items = sorted((i for i in items if self.wanted(i[0])), key=lambda i: -i[0].rank)
        shown, rest = items[:self.cfg.max_per_batch], items[self.cfg.max_per_batch:]
        for d, ai in shown:
            for s in self.sinks:
                try:
                    s.send(d, ai)
                except Exception:
                    pass
        if rest:
            for s in self.sinks:
                try:
                    s.summary(f"+{len(rest)} more problem(s). Run `aiterm analyze` to list them.")
                except Exception:
                    pass
        return len(shown)
