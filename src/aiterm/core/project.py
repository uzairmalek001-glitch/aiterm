"""Project & language detection."""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from aiterm.analyzers.base import all_analyzers

MARKERS = ["pyproject.toml", "setup.py", "requirements.txt", "package.json", "tsconfig.json", "Cargo.toml",
           "pom.xml", "build.gradle", "build.gradle.kts", "CMakeLists.txt", "Makefile"]


@dataclass
class ProjectInfo:
    root: Path
    languages: List[str] = field(default_factory=list)
    markers: List[str] = field(default_factory=list)
    is_git: bool = False
    file_count: int = 0


def find_root(start: Path) -> Path:
    start = Path(start).resolve()
    for p in [start, *start.parents]:
        if (p / ".git").exists() or (p / "aiterm.toml").exists():
            return p
    return start


def detect_project(root: Path, ignore_dirs, limit: int = 5000) -> ProjectInfo:
    root = Path(root).resolve()
    ext_lang = {e: a.name for a in all_analyzers() for e in a.extensions}
    counts: Counter = Counter()
    n = 0
    ignore = set(ignore_dirs)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore]
        for fn in filenames:
            lang = ext_lang.get(os.path.splitext(fn)[1])
            if lang:
                counts[lang] += 1
            n += 1
            if n >= limit:
                break
        if n >= limit:
            break
    return ProjectInfo(root, [l for l, _ in counts.most_common()],
                       [m for m in MARKERS if (root / m).exists()], (root / ".git").exists(), n)
