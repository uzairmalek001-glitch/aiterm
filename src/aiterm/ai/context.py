"""Minimal, redacted context for the AI. Never the whole repo; never sensitive files."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

from aiterm.core.config import AIConfig
from aiterm.core.models import Diagnostic
from aiterm.security.redact import find_secrets, is_sensitive_path, redact


@dataclass
class Context:
    text: str
    files: List[str]
    redacted: bool          # True if any secret-like content was masked


def _slice(path: Path, line: int, n: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lo, hi = max(0, line - 1 - n), min(len(lines), line + n)
    return "\n".join(f"{i + 1:>4} | {lines[i]}" for i in range(lo, hi))


def _enclosing_function(path: Path, line: int) -> str:
    if path.suffix != ".py":
        return ""
    import ast
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, ValueError, OSError):
        return ""
    best = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno <= line <= (n.end_lineno or n.lineno):
            if best is None or n.lineno > best.lineno:
                best = n
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[best.lineno - 1:best.end_lineno]) if best else ""


def _imports(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:200]
    except OSError:
        return ""
    return "\n".join(l for l in lines if re.match(r"\s*(import |from .+ import |#include|use |package |using )", l))


def _recent_diff(root: Path, file: str, limit: int = 1500) -> str:
    if not (root / ".git").exists():
        return ""
    try:
        p = subprocess.run(["git", "diff", "-U2", "--", file], cwd=root, capture_output=True, text=True, timeout=5)
        return p.stdout[:limit]
    except (OSError, subprocess.TimeoutExpired):
        return ""


def build_context(d: Diagnostic, root: Path, cfg: AIConfig, languages=()) -> Context:
    root = Path(root)
    parts = ["## DETECTED FACT (from deterministic tooling)",
             f"tool={d.source} category={d.category} severity={d.severity} file={d.file} line={d.line} col={d.column}",
             f"message: {d.message}"]
    if d.raw and d.raw != d.message:
        parts += ["raw output / stack trace:", d.raw[:1500]]
    files: List[str] = []
    p = (root / d.file)
    try:
        inside = p.resolve().is_relative_to(root.resolve())
    except OSError:
        inside = False
    if not inside or not p.is_file():
        parts.append("(source file unavailable)")
    elif is_sensitive_path(p):
        parts.append("(source file withheld: matches a sensitive-file pattern)")
    else:
        files.append(d.file)
        if d.line:
            parts += ["## RELEVANT SOURCE LINES", _slice(p, d.line, cfg.context_lines)]
            fn = _enclosing_function(p, d.line)
            if fn and len(fn) < 2500:
                parts += ["## ENCLOSING FUNCTION", fn]
        imps = _imports(p)
        if imps:
            parts += ["## IMPORTS", imps]
        diff = _recent_diff(root, d.file)
        if diff:
            parts += ["## RECENT CHANGES (git diff)", diff]
    if languages:
        parts += ["## PROJECT", "languages: " + ", ".join(languages)]
    raw_text = "\n".join(parts)
    secret = bool(find_secrets(raw_text))
    text = redact(raw_text)[:cfg.max_context_chars]
    return Context(text, files, secret)
