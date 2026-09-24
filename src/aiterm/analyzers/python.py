"""Python analyzer: ast syntax check, import resolution (incl. renamed/moved names), optional ruff."""
from __future__ import annotations

import ast
import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Set

from aiterm.analyzers.base import LanguageAnalyzer, rel, register, run_tool
from aiterm.analyzers.classify import classify
from aiterm.analyzers.fixes import local_fix, local_hint
from aiterm.core.models import Category, Diagnostic

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", ".aiterm", "target"}


def _local_module(root: Path, here: Path, dotted: str) -> Optional[Path]:
    parts = dotted.split(".")
    for base in (root, root / "src", here.parent):
        p = base.joinpath(*parts)
        if p.with_suffix(".py").is_file():
            return p.with_suffix(".py")
        if (p / "__init__.py").is_file():
            return p / "__init__.py"
    return None


def _defined_names(tree: ast.AST) -> Set[str]:
    names: Set[str] = set()
    for n in getattr(tree, "body", []):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                names.update(x.id for x in ast.walk(t) if isinstance(x, ast.Name))
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)) and isinstance(n.target, ast.Name):
            names.add(n.target.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, (ast.If, ast.Try)):  # conditional definitions: be permissive
            names |= _defined_names(n)
    return names


def _dotted_for(root: Path, f: Path) -> str:
    r = f.relative_to(root)
    parts = list(r.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def find_definition(root: Path, name: str, limit: int = 2000) -> Optional[Path]:
    """Locate a class/function by name elsewhere in the project (only run after an import failure)."""
    seen = 0
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            seen += 1
            if seen > limit:
                return None
            p = Path(dp, fn)
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, OSError, UnicodeDecodeError, ValueError):
                continue
            for n in tree.body:
                if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
                    return p
    return None


def _guarded_import_nodes(tree: ast.AST) -> Set[int]:
    guarded: Set[int] = set()
    for t in ast.walk(tree):
        if isinstance(t, ast.Try):
            for h in t.handlers:
                nm = ast.unparse(h.type) if h.type else "Exception"
                if any(k in nm for k in ("ImportError", "ModuleNotFoundError", "Exception")) or h.type is None:
                    for b in t.body:
                        guarded.update(id(x) for x in ast.walk(b))
    return guarded


@register
class PythonAnalyzer(LanguageAnalyzer):
    name = "python"
    extensions = (".py",)
    use_ruff = True

    def analyze(self, path: Path, root: Path) -> List[Diagnostic]:
        try:
            src = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []
        r = rel(path, root)
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError as e:
            lines = src.splitlines()
            msg = e.msg or "invalid syntax"
            ln = e.lineno or 1
            return [Diagnostic(r, ln, e.offset or 0, "error", Category.SYNTAX_ERROR, msg, "python",
                               fix_line=local_fix(msg, lines, ln), hint=local_hint(msg),
                               raw=f"{type(e).__name__}: {msg} ({r}:{ln})")]
        except ValueError as e:  # e.g. null bytes
            return [Diagnostic(r, 1, 0, "error", Category.SYNTAX_ERROR, str(e), "python")]
        diags = self._imports(tree, path, root, r, src.splitlines())
        if self.use_ruff:
            diags += self._ruff(path, root, r)
        return diags

    def _imports(self, tree, path, root, r, lines) -> List[Diagnostic]:
        out: List[Diagnostic] = []
        guarded = _guarded_import_nodes(tree)
        stdlib = getattr(sys, "stdlib_module_names", set())
        for n in ast.walk(tree):
            if id(n) in guarded:
                continue
            if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                top = n.module.split(".")[0]
                local = _local_module(root, path, n.module)
                if local is not None and local.resolve() != path.resolve():
                    try:
                        defined = _defined_names(ast.parse(local.read_text(encoding="utf-8")))
                    except (SyntaxError, OSError, UnicodeDecodeError):
                        continue
                    for a in n.names:
                        if a.name != "*" and a.name not in defined and not (local.parent / a.name).exists() \
                                and not (local.parent / f"{a.name}.py").exists():
                            out.append(self._missing_name(n, a, r, root, lines))
                    continue
                if top not in stdlib and self._missing(top, root, path):
                    out.append(self._missing_mod(n, top, r))
            elif isinstance(n, ast.Import):
                for a in n.names:
                    top = a.name.split(".")[0]
                    if top not in stdlib and _local_module(root, path, top) is None and self._missing(top, root, path):
                        out.append(self._missing_mod(n, top, r))
        return out

    @staticmethod
    def _missing(top: str, root: Path, path: Path) -> bool:
        try:
            if importlib.util.find_spec(top) is not None:
                return False
        except (ImportError, ValueError, AttributeError):
            pass
        return not (root / top).exists() and not (root / f"{top}.py").exists() and not (root / "src" / top).exists()

    @staticmethod
    def _missing_mod(n, top, r) -> Diagnostic:
        msg = f"No module named '{top}'"
        return Diagnostic(r, n.lineno, n.col_offset + 1, "warning", Category.IMPORT_ERROR, msg, "python",
                          hint="Not installed in the current environment (or wrong import path). "
                               "If you use another virtualenv, this may be a false positive.")

    def _missing_name(self, n, alias, r, root, lines) -> Diagnostic:
        msg = f"cannot import name '{alias.name}' from '{n.module}'"
        fix = hint = None
        where = find_definition(root, alias.name)
        if where is not None:
            dotted = _dotted_for(root, where)
            hint = f"'{alias.name}' is defined in {rel(where, root)}."
            if len(n.names) == 1 and 1 <= n.lineno <= len(lines):
                indent = re.match(r"\s*", lines[n.lineno - 1]).group(0)
                asname = f" as {alias.asname}" if alias.asname else ""
                fix = f"{indent}from {dotted} import {alias.name}{asname}"
        return Diagnostic(r, n.lineno, n.col_offset + 1, "error", Category.IMPORT_ERROR, msg, "python",
                          fix_line=fix, hint=hint or local_hint(msg))

    def _ruff(self, path: Path, root: Path, r: str) -> List[Diagnostic]:
        res = run_tool(["ruff", "check", "--output-format=concise", "--no-cache", str(path)], root, 15)
        if not res:
            return []
        out = []
        for m in re.finditer(r"^.+?:(\d+):(\d+): (\S+) (.+)$", res[1], re.M):
            code, msg = m[3], m[4]
            cat = Category.SECURITY_WARNING if code.startswith("S") else \
                Category.LOGIC_WARNING if code[:2] in ("F8", "F6", "B0") else Category.LINT_ERROR
            out.append(Diagnostic(r, int(m[1]), int(m[2]), "warning", cat, f"{code}: {msg}", "ruff"))
        return out
