"""Deterministic (no-AI) hints and single-line fixes for well-understood errors."""
from __future__ import annotations

import re
from typing import List, Optional

_HINTS = [
    (r"expected ':'", "A block header (for/if/def/class/while/else/try...) must end with a colon."),
    (r"was never closed", "An opening bracket or quote has no matching closing one."),
    (r"invalid syntax", "Python could not parse this line; look at the token just before the reported position."),
    (r"unexpected indent|expected an indented block|unindent", "Indentation is inconsistent with the surrounding block."),
    (r"cannot import name", "The module exists but does not define that name; it may have been renamed or moved."),
    (r"no module named", "The module is not installed in this environment or the import path is wrong."),
    (r"expected ';'", "A statement is missing its terminating semicolon (often reported on the following line)."),
    (r"no matching function", "No overload accepts these argument types/counts."),
    (r"undeclared|not declared|cannot find symbol|cannot find value", "A name is used before it is declared or is misspelled."),
]


def local_hint(message: str) -> str:
    for pat, text in _HINTS:
        if re.search(pat, message, re.IGNORECASE):
            return text
    return ""


def local_fix(message: str, lines: List[str], lineno: int) -> Optional[str]:
    """Return a replacement for line `lineno` (no trailing newline), or None."""
    if not (1 <= lineno <= len(lines)):
        return None
    line = lines[lineno - 1].rstrip("\r\n")
    if re.search(r"expected ':'", message) and not line.rstrip().endswith(":"):
        return line.rstrip() + ":"
    return None
