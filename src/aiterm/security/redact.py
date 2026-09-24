"""Secret detection & redaction. Runs on EVERYTHING before it can leave the machine or hit a log."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import List, Tuple

MASK = "********"

SENSITIVE_GLOBS = [".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_dsa*",
                   "id_ecdsa*", "id_ed25519*", "*.keystore", "*.jks", ".npmrc", ".netrc", ".pypirc",
                   "credentials", "credentials.*", "secrets.*", "*.kdbx", ".git-credentials", "*.tfvars"]

_PATTERNS: List[Tuple[str, "re.Pattern"]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S)),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("api_key_sk", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("bearer", re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/\-]{16,}=*")),
    ("url_credentials", re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+:)[^\s@/]+(@)")),
]
# NAME = value / NAME: value / "name": "value"  where NAME looks secret-ish
_ASSIGN = re.compile(
    r"""(?ix)
    (?P<key>["']?[A-Za-z0-9_.\-]*(?:api[_\-]?key|secret|passw(?:or)?d|passwd|pwd|token|private[_\-]?key|
        access[_\-]?key|auth|credential)[A-Za-z0-9_.\-]*["']?)
    (?P<sep>\s*[:=]\s*)
    (?P<val>"[^"\n]*"|'[^'\n]*'|[^\s,;#'"]+)
    """)


def is_sensitive_path(path) -> bool:
    name = Path(path).name.lower()
    return any(fnmatch.fnmatch(name, g.lower()) for g in SENSITIVE_GLOBS)


def find_secrets(text: str) -> List[str]:
    kinds = [k for k, rx in _PATTERNS if rx.search(text)]
    if any(_is_real_assign(m) for m in _ASSIGN.finditer(text)):
        kinds.append("credential_assignment")
    return kinds


def _is_real_assign(m: "re.Match") -> bool:
    val = m["val"].strip("\"'")
    return bool(val) and val != MASK and not val.startswith(("$", "{", "<", "os.", "env", "None", "null", "process."))\
        and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\(.*\)?", val or "x") and len(val) >= 3


def redact(text: str) -> str:
    if not text:
        return text
    for kind, rx in _PATTERNS:
        if kind == "bearer":
            text = rx.sub(lambda m: f"{m.group(1)} {MASK}", text)
        elif kind == "url_credentials":
            text = rx.sub(lambda m: f"{m.group(1)}{MASK}{m.group(2)}", text)
        elif kind == "private_key":
            text = rx.sub("-----BEGIN PRIVATE KEY-----\n" + MASK + "\n-----END PRIVATE KEY-----", text)
        else:
            text = rx.sub(MASK, text)

    def sub(m: "re.Match") -> str:
        if not _is_real_assign(m):
            return m.group(0)
        v = m["val"]
        q = v[0] if v[0] in "\"'" else ""
        return f'{m["key"]}{m["sep"]}{q}{MASK}{q}'

    return _ASSIGN.sub(sub, text)
