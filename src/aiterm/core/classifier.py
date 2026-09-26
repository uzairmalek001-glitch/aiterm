"""Deterministic diagnostic classification.

This module classifies diagnostics from observable evidence only.
It never uses AI and never guesses when evidence is ambiguous.
"""

from __future__ import annotations

import re

from aiterm.core.models import Category, Diagnostic


_RULES = (
    (
        Category.CONFIGURATION_ERROR,
        (
            r"\binvalid\s+(?:yaml|yml|json|toml|configuration|config)\b",
            r"\b(?:yaml|yml|json|toml)\s+(?:parser|parse)\b",
            r"\bconfiguration\s+(?:error|invalid|failed)\b",
            r"\binvalid\s+configuration\b",
        ),
    ),
    (
        Category.SYNTAX_ERROR,
        (
            r"\bsyntax\s+error\b",
            r"\bsyntaxerror\b",
            r"\bparse\s+error\b",
        ),
    ),
    (
        Category.TYPE_ERROR,
        (
            r"\btype\s+error\b",
            r"\btypeerror\b",
        ),
    ),
    (
        Category.IMPORT_ERROR,
        (
            r"\bimport\s+error\b",
            r"\bimporterror\b",
            r"\bmodulenotfounderror\b",
        ),
    ),
    (
        Category.DEPENDENCY_ERROR,
        (
            r"\bno\s+module\s+named\b",
            r"\bmissing\s+(?:dependency|package)\b",
            r"\bdependency\s+(?:error|missing)\b",
        ),
    ),
    (
        Category.RUNTIME_ERROR,
        (
            r"\btraceback\s+\(most\s+recent\s+call\s+last\)",
            r"\bruntime\s+error\b",
            r"\b(?:name|key|index|attribute|value)error\b",
        ),
    ),
    (
        Category.TEST_FAILURE,
        (
            r"\btest\s+failed\b",
            r"\btests?\s+failed\b",
            r"(?m)^\s*FAILED\b",
            r"\bassert(?:ion)?\s+(?:error|failed|failure)\b",
        ),
    ),
    (
        Category.COMPILATION_ERROR,
        (
            r"\bcompilation\s+error\b",
            r"\bcompile\s+error\b",
            r"\berror:\s+.*\b(?:gcc|g\+\+|clang|javac)\b",
        ),
    ),
)


_COMPILED_RULES = tuple(
    (category, tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns))
    for category, patterns in _RULES
)


def classify(diagnostic: Diagnostic) -> str:
    """Return the strongest deterministic category supported by the evidence."""

    if diagnostic.category != Category.UNKNOWN.value:
        return diagnostic.category

    evidence = "\n".join(
        part for part in (diagnostic.message, diagnostic.raw, diagnostic.hint)
        if part
    )

    for category, patterns in _COMPILED_RULES:
        if any(pattern.search(evidence) for pattern in patterns):
            return category.value

    return Category.UNKNOWN.value
