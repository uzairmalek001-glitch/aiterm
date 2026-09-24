"""Parse terminal output (tracebacks, compiler errors, test failures) into Diagnostics."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from aiterm.analyzers.base import rel
from aiterm.analyzers.classify import classify
from aiterm.analyzers.fixes import local_hint
from aiterm.analyzers.parsers import parse_gcc_style, parse_tsc
from aiterm.core.models import Category, Diagnostic

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\r")
PY_FRAME = re.compile(r'File "([^"]+)", line (\d+)')
PY_TB = re.compile(r"Traceback \(most recent call last\):\n((?:[ \t]+.*\n|\n)*?)(?P<exc>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Warning)?)(?::[ \t]*(?P<msg>.*))?$", re.M)
PYTEST_FAIL = re.compile(r"^FAILED (?P<file>[^\s:]+)(?:::(?P<test>\S+))?(?: - (?P<msg>.*))?$", re.M)
NODE_ERR = re.compile(r"^(?P<kind>(?:Type|Reference|Range|Syntax)Error): (?P<msg>.+)$", re.M)
NODE_FRAME = re.compile(r"at (?:.+? \()?(?P<file>[^\s()]+):(?P<line>\d+):(?P<col>\d+)\)?")
RUST_PANIC = re.compile(r"thread '.*?' panicked at (?P<file>[^:\s]+):(?P<line>\d+):(?P<col>\d+):?\s*\n?(?P<msg>.*)")


def strip_ansi(s: str) -> str:
    return ANSI.sub("", s)


def _in_project(p: str, root: Path) -> bool:
    try:
        return Path(p).resolve().is_relative_to(Path(root).resolve()) and "site-packages" not in p
    except (OSError, ValueError):
        return False


def parse_output(text: str, root: Path, source: str = "terminal") -> List[Diagnostic]:
    text = strip_ansi(text)
    root = Path(root)
    out: List[Diagnostic] = []

    for m in PY_TB.finditer(text):
        block = m.group(0)
        frames = PY_FRAME.findall(block)
        mine = [f for f in frames if _in_project(f[0] if Path(f[0]).is_absolute() else str(root / f[0]), root)]
        f, ln = (mine or frames or [("<unknown>", "0")])[-1]
        exc, msg = m["exc"], (m["msg"] or "").strip()
        full = f"{exc}: {msg}" if msg else exc
        cat = Category.IMPORT_ERROR if exc.endswith(("ImportError", "ModuleNotFoundError")) else \
            Category.SYNTAX_ERROR if exc.endswith("SyntaxError") else Category.RUNTIME_ERROR
        out.append(Diagnostic(rel(Path(f), root) if Path(f).is_absolute() else f, int(ln), 0, "error", cat, full,
                              "python-runtime", hint=local_hint(full), raw=block[-1500:]))

    for m in PYTEST_FAIL.finditer(text):
        msg = f'{m["test"] or "test"} failed' + (f': {m["msg"]}' if m["msg"] else "")
        out.append(Diagnostic(m["file"], 0, 0, "error", Category.TEST_FAILURE, msg, "pytest", raw=m.group(0)))

    out += parse_gcc_style(text, source, root)
    out += parse_tsc(text, root)

    for m in RUST_PANIC.finditer(text):
        out.append(Diagnostic(m["file"], int(m["line"]), int(m["col"]), "error", Category.RUNTIME_ERROR,
                              f'panic: {m["msg"].strip()}', "rust-runtime", raw=m.group(0)))

    e = NODE_ERR.search(text)
    if e:
        fr = next((f for f in NODE_FRAME.finditer(text) if _in_project(f["file"], root)), None)
        if fr:
            full = f'{e["kind"]}: {e["msg"]}'
            cat = Category.SYNTAX_ERROR if e["kind"] == "SyntaxError" else Category.RUNTIME_ERROR
            out.append(Diagnostic(rel(Path(fr["file"]), root), int(fr["line"]), int(fr["col"]), "error", cat, full,
                                  "node-runtime", raw=text[-1200:]))

    seen, uniq = set(), []
    for d in out:
        if d.fingerprint not in seen:
            seen.add(d.fingerprint)
            uniq.append(d)
    return uniq
