"""LanguageAnalyzer interface + registry. Add a language = add one class and @register it."""
from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

from aiterm.core.models import Diagnostic


class LanguageAnalyzer(ABC):
    name: str = ""
    extensions: Tuple[str, ...] = ()

    def available(self) -> bool:
        return True

    @abstractmethod
    def analyze(self, path: Path, root: Path) -> List[Diagnostic]:
        """Return deterministic diagnostics for one file. Must never raise for bad user code."""


_REGISTRY: Dict[str, LanguageAnalyzer] = {}


def register(cls: Type[LanguageAnalyzer]) -> Type[LanguageAnalyzer]:
    inst = cls()
    _REGISTRY[inst.name] = inst
    return cls


def all_analyzers() -> List[LanguageAnalyzer]:
    _load_builtin()
    return list(_REGISTRY.values())


def get_analyzer(path: Path) -> Optional[LanguageAnalyzer]:
    _load_builtin()
    for a in _REGISTRY.values():
        if path.suffix in a.extensions:
            return a
    return None


def known_extensions() -> List[str]:
    return [e for a in all_analyzers() for e in a.extensions]


_LOADED = False


def _load_builtin() -> None:
    global _LOADED
    if not _LOADED:
        _LOADED = True
        from aiterm.analyzers import python, tools  # noqa: F401  (registration side effects)


def run_tool(cmd: List[str], cwd: Path, timeout: float = 30.0) -> Optional[Tuple[int, str]]:
    """Run an external checker. None means 'tool missing / timed out' (never an error for the user)."""
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, errors="replace",
                           env={**os.environ, "LC_ALL": "C", "LANG": "C", "NO_COLOR": "1"})
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
        return None
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def rel(path: Path, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)
