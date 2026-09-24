"""Append-only local history (JSONL). Crash-safe: corrupt/partial lines are skipped. Never leaves the machine."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from aiterm.core.models import Diagnostic
from aiterm.security.redact import redact


class History:
    def __init__(self, root: Path):
        self.dir = Path(root) / ".aiterm"
        self.path = self.dir / "history.jsonl"

    def _append(self, rec: dict) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            lead = ""
            if self.path.exists() and self.path.stat().st_size:
                with self.path.open("rb") as fb:      # a crash may have left a torn last line
                    fb.seek(-1, 2)
                    lead = "" if fb.read(1) == b"\n" else "\n"
            with self.path.open("a", encoding="utf-8") as f:
                f.write(lead + json.dumps(rec) + "\n")
        except OSError:
            pass

    def record(self, d: Diagnostic) -> None:
        rec = d.to_dict()
        rec["message"], rec["raw"] = redact(rec["message"]), redact(rec.get("raw", ""))
        self._append({"type": "diag", **rec})

    def record_ai(self, diag_id: str, ai: dict) -> None:
        self._append({"type": "ai", "id": diag_id, "ai": {k: redact(v) if isinstance(v, str) else v for k, v in ai.items()}})

    def entries(self) -> List[dict]:
        latest: Dict[str, dict] = {}
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        for ln in lines:
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue  # partial write from a crash
            if not isinstance(r, dict) or "id" not in r:
                continue
            if r.get("type") == "ai":
                if r["id"] in latest:
                    latest[r["id"]]["ai"] = r.get("ai")
            else:
                prev = latest.get(r["id"], {})
                latest[r["id"]] = {**r, "ai": prev.get("ai")}
        return list(latest.values())

    def get(self, id_prefix: str) -> Optional[Diagnostic]:
        hits = [e for e in self.entries() if e["id"].startswith(id_prefix)]
        return Diagnostic.from_dict(hits[-1]) if hits else None
