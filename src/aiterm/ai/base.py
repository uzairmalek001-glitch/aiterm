"""AI provider abstraction + structured result."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Optional


class AIUnavailable(Exception):
    """Provider unreachable / misconfigured / timed out. Callers degrade to local diagnostics."""


class AIProvider(ABC):
    name = "base"

    @abstractmethod
    def complete(self, system: str, user: str) -> str: ...


@dataclass
class AIResult:
    """AI *inference*. Always displayed separately from detected facts."""
    problem: str = ""
    cause: str = ""
    explanation: str = ""
    suggested_fix: str = ""
    fixed_line: Optional[str] = None   # optional single-line replacement usable for a patch
    confidence: float = 0.0
    requires_manual_review: bool = True
    provider: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def parse_ai_json(text: str, provider: str = "") -> AIResult:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    a, b = t.find("{"), t.rfind("}")
    try:
        d = json.loads(t[a:b + 1]) if a != -1 and b > a else None
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict):  # model ignored the format: keep text, flag for review
        return AIResult(explanation=(text or "").strip()[:1500], confidence=0.0,
                        requires_manual_review=True, provider=provider)
    try:
        conf = max(0.0, min(1.0, float(d.get("confidence", 0.0))))
    except (TypeError, ValueError):
        conf = 0.0
    fl = d.get("fixed_line")
    return AIResult(str(d.get("problem", "")), str(d.get("cause", "")), str(d.get("explanation", "")),
                    str(d.get("suggested_fix", "")), fl if isinstance(fl, str) and "\n" not in fl.strip("\n") else None,
                    conf, bool(d.get("requires_manual_review", conf < 0.7)), provider)
