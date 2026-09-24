"""Error classifier: message text -> Category."""
from __future__ import annotations

import re
from typing import List, Tuple

from aiterm.core.models import Category

_RULES: List[Tuple[str, Category]] = [
    (r"syntaxerror|invalid syntax|expected ['\"`]?[;:,)}\]]|unexpected token|unterminated|was never closed|"
     r"unexpected eof|indentation|expected .* before|missing ['\"]?[;)}\]]|premature end|reached end of file|at end of input|expected declaration or statement|missing terminating|"
     r"TS1\d{3}|';' expected|'\)' expected", Category.SYNTAX_ERROR),
    (r"no module named|cannot import name|cannot find module|module not found|unresolved import|"
     r"could not be resolved|package .* does not exist|E0432|E0433|TS2307|no such file or directory|file not found", Category.IMPORT_ERROR),
    (r"no matching distribution|version conflict|unresolved dependency|could not resolve dependenc|"
     r"dependency .* not found|peer dep", Category.DEPENDENCY_ERROR),
    (r"pyproject|tsconfig|cargo\.toml|pom\.xml|build\.gradle|invalid configuration|config file", Category.CONFIGURATION_ERROR),
    (r"\btype\b|incompatible|not assignable|mismatched types|E0308|cannot convert|no matching function|"
     r"TS2\d{3}|invalid conversion|too (many|few) arguments", Category.TYPE_ERROR),
    (r"hardcoded|hard-coded|injection|insecure|\beval\b|\bexec\b|shell=true|pickle|md5|B\d{3}\b", Category.SECURITY_WARNING),
    (r"slow|inefficient|performance|quadratic|unnecessary (copy|allocation)", Category.PERFORMANCE_WARNING),
    (r"unused|undefined name|unreachable|shadow|always (true|false)|self-assign|division by zero", Category.LOGIC_WARNING),
    (r"assert|test failed|\bFAILED\b", Category.TEST_FAILURE),
]


def classify(message: str, default: Category = Category.COMPILATION_ERROR) -> Category:
    for pat, cat in _RULES:
        if re.search(pat, message, re.IGNORECASE):
            return cat
    return default
