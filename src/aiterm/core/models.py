"""Structured diagnostics shared by every component."""
from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Optional


class Category(str, Enum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    TYPE_ERROR = "TYPE_ERROR"
    IMPORT_ERROR = "IMPORT_ERROR"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TEST_FAILURE = "TEST_FAILURE"
    LINT_ERROR = "LINT_ERROR"
    SECURITY_WARNING = "SECURITY_WARNING"
    LOGIC_WARNING = "LOGIC_WARNING"
    PERFORMANCE_WARNING = "PERFORMANCE_WARNING"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2, "critical": 3}


def _val(x) -> str:
    return x.value if isinstance(x, Enum) else str(x)


@dataclass
class Diagnostic:
    """A deterministic, tool-detected fact. AI opinions live elsewhere (AIResult)."""

    file: str
    line: int
    column: int
    severity: str
    category: str
    message: str
    source: str
    timestamp: str = ""
    fingerprint: str = ""
    id: str = ""
    fix_line: Optional[str] = None  # deterministic replacement for `line`, if known
    hint: str = ""                  # deterministic explanation, if known
    raw: str = ""                   # raw tool output / stack trace (never sent unredacted)

    def __post_init__(self) -> None:
        self.severity = _val(self.severity)
        self.category = _val(self.category)
        if not self.timestamp:
            self.timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        if not self.fingerprint:
            key = f"{self.file}:{self.line}:{self.category}:{self.message}"
            self.fingerprint = hashlib.sha1(key.encode()).hexdigest()[:16]
        self.id = self.fingerprint[:8]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Diagnostic":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    @property
    def rank(self) -> int:
        return SEVERITY_RANK.get(self.severity, 0)
