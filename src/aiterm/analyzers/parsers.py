"""Parsers for common compiler/tool output formats -> Diagnostic."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from aiterm.analyzers.base import rel
from aiterm.analyzers.classify import classify
from aiterm.analyzers.fixes import local_hint
from aiterm.core.models import Category, Diagnostic

# gcc/clang/kotlinc/rustc(short):  file:line[:col]: error[E0425]: message     javac: File.java:3: error: msg
GCC_RE = re.compile(r"^(?P<file>[^\s:(][^:\n]*?):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
                    r"(?P<sev>fatal error|error|warning)(?:\[[A-Z0-9]+\])?:\s*(?P<msg>.+)$", re.M)
# tsc:  file.ts(3,5): error TS1005: ';' expected.
TSC_RE = re.compile(r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<sev>error|warning)\s+(?P<code>TS\d+):\s*(?P<msg>.+)$", re.M)


def _sev(s: str) -> str:
    return "warning" if s == "warning" else "error"


def _mk(file, line, col, sev, msg, source, root, raw, default=Category.COMPILATION_ERROR) -> Diagnostic:
    p = Path(file)
    if not p.is_absolute():
        p = Path(root) / p
    return Diagnostic(rel(p, root), int(line), int(col or 0), _sev(sev), classify(msg, default), msg.strip(),
                      source, hint=local_hint(msg), raw=raw)


def parse_gcc_style(output: str, source: str, root: Path) -> List[Diagnostic]:
    out = []
    for m in GCC_RE.finditer(output):
        out.append(_mk(m["file"], m["line"], m["col"], m["sev"], m["msg"], source, root, m.group(0)))
    return out


def parse_tsc(output: str, root: Path) -> List[Diagnostic]:
    out = []
    for m in TSC_RE.finditer(output):
        msg = f'{m["code"]}: {m["msg"]}'
        out.append(_mk(m["file"], m["line"], m["col"], m["sev"], msg, "typescript", root, m.group(0)))
    return out


def parse_node_check(output: str, path: Path, root: Path) -> List[Diagnostic]:
    """`node --check f.js` prints 'f.js:LINE', the code line, a caret line, then 'SyntaxError: msg'."""
    m = re.search(r"^(?P<file>.+?):(?P<line>\d+)\s*$", output, re.M)
    e = re.search(r"^(?P<kind>\w*Error): (?P<msg>.+)$", output, re.M)
    if not e:
        return []
    line = int(m["line"]) if m else 1
    msg = f'{e["kind"]}: {e["msg"]}'
    return [Diagnostic(rel(path, root), line, 0, "error", Category.SYNTAX_ERROR, msg, "javascript",
                       hint=local_hint(msg), raw=output.strip()[:1000])]
