"""Patch generation & (explicitly approved) application. Nothing is ever modified silently."""
from __future__ import annotations

import difflib
import hashlib
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


class PatchError(Exception):
    pass


@dataclass
class PatchProposal:
    file: str
    original_sha: str
    new_text: str
    diff: str
    description: str = ""


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class PatchManager:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _path(self, file: str) -> Path:
        p = (self.root / file).resolve()
        if not p.is_relative_to(self.root):
            raise PatchError("refusing to touch a file outside the project")
        if not p.is_file():
            raise PatchError(f"{file} does not exist")
        return p

    def propose_text(self, file: str, new_text: str, description: str = "") -> PatchProposal:
        p = self._path(file)
        raw = p.read_bytes()
        old = raw.decode("utf-8", errors="replace")
        diff = "".join(difflib.unified_diff(old.splitlines(True), new_text.splitlines(True),
                                            f"a/{file}", f"b/{file}"))
        return PatchProposal(file, _sha(raw), new_text, diff, description)

    def propose_line_fix(self, file: str, line: int, new_line: str, description: str = "") -> PatchProposal:
        p = self._path(file)
        text = p.read_bytes().decode("utf-8", errors="replace")   # keep CRLF as-is
        lines = text.splitlines(True)
        if not 1 <= line <= len(lines):
            raise PatchError(f"line {line} is out of range")
        old = lines[line - 1]
        eol = re.search(r"(\r\n|\n|\r)$", old)
        eol = eol.group(1) if eol else ""
        new_line = new_line.rstrip("\r\n")
        if not new_line[:1].isspace():  # AI often omits indentation
            new_line = re.match(r"\s*", old).group(0) + new_line
        lines[line - 1] = new_line + eol
        return self.propose_text(file, "".join(lines), description)

    def apply(self, proposal: PatchProposal, *, approved: bool) -> Path:
        """Apply only with explicit approval and only if the file is unchanged since proposal."""
        if approved is not True:
            raise PatchError("explicit user approval is required to modify source files")
        p = self._path(proposal.file)
        if _sha(p.read_bytes()) != proposal.original_sha:
            raise PatchError("file changed since the patch was proposed; re-run analysis")
        bdir = self.root / ".aiterm" / "backups"
        bdir.mkdir(parents=True, exist_ok=True)
        backup = bdir / f"{int(time.time())}-{p.name}.bak"
        shutil.copy2(p, backup)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".aiterm-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(proposal.new_text)
            shutil.copymode(p, tmp)
            os.replace(tmp, p)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return backup

    def restore(self, backup: Path, file: str) -> None:
        shutil.copy2(backup, self._path(file))
