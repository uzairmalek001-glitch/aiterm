"""Deterministic evidence-based diagnosis layer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from aiterm.core.classifier import classify
from aiterm.core.models import Category, Diagnostic


@dataclass
class Diagnosis:
    """Evidence-backed interpretation of a diagnostic."""

    category: str
    cause: str
    confidence: str
    evidence: List[str] = field(default_factory=list)
    verification: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "cause": self.cause,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "verification": self.verification,
        }


def diagnose(diagnostic: Diagnostic) -> Diagnosis:
    """Produce a deterministic diagnosis from observable diagnostic evidence."""

    category = classify(diagnostic)

    evidence_text = "\n".join(
        part
        for part in (
            diagnostic.message,
            diagnostic.raw,
            diagnostic.hint,
        )
        if part
    )

    if category == Category.CONFIGURATION_ERROR.value:
        evidence = []

        if re.search(r"\binvalid\s+yaml\b", evidence_text, re.I):
            evidence.append("invalid YAML")

        if "]" in evidence_text and re.search(r"expected", evidence_text, re.I):
            evidence.append("parser expected a closing bracket")

        if "," in evidence_text and re.search(r"expected", evidence_text, re.I):
            evidence.append("parser expected a comma")

        if re.search(r"\bat\s+line\s+\d+\b", evidence_text, re.I):
            evidence.append(f"parser reported an error at line {diagnostic.line}")

        cause = "malformed YAML configuration"

        return Diagnosis(
            category=category,
            cause=cause,
            confidence="high" if evidence else "medium",
            evidence=evidence,
            verification=(
                f"Inspect {diagnostic.file} around line {diagnostic.line} "
                "and validate the configuration syntax."
            ),
        )

    if category == Category.SYNTAX_ERROR.value:
        return Diagnosis(
            category=category,
            cause="source code contains a syntax error",
            confidence="high",
            evidence=["syntax error reported by the tool"],
            verification=(
                f"Inspect {diagnostic.file} around line {diagnostic.line}."
            ),
        )

    if category == Category.TYPE_ERROR.value:
        return Diagnosis(
            category=category,
            cause="an operation received an incompatible type",
            confidence="high",
            evidence=["type error reported by the tool"],
            verification=(
                f"Inspect {diagnostic.file} around line {diagnostic.line} "
                "and check the involved values and types."
            ),
        )

    if category == Category.IMPORT_ERROR.value:
        return Diagnosis(
            category=category,
            cause="an import could not be resolved",
            confidence="high",
            evidence=["import-related error reported by the tool"],
            verification="Check the import path and available modules.",
        )

    if category == Category.DEPENDENCY_ERROR.value:
        return Diagnosis(
            category=category,
            cause="a required dependency is unavailable",
            confidence="high",
            evidence=["missing dependency reported by the tool"],
            verification="Check the project's declared and installed dependencies.",
        )

    if category == Category.TEST_FAILURE.value:
        return Diagnosis(
            category=category,
            cause="a test reported a failure",
            confidence="high",
            evidence=["test failure reported by the test runner"],
            verification="Run the failing test independently and inspect its assertion.",
        )

    if category == Category.RUNTIME_ERROR.value:
        return Diagnosis(
            category=category,
            cause="the program raised a runtime exception",
            confidence="high",
            evidence=["runtime exception reported by the program"],
            verification=(
                f"Inspect {diagnostic.file} around line {diagnostic.line} "
                "and trace the reported exception."
            ),
        )

    return Diagnosis(
        category=Category.UNKNOWN.value,
        cause="insufficient deterministic evidence to identify the cause",
        confidence="low",
        evidence=[],
        verification="Collect more diagnostic output before proposing a cause.",
    )
