"""AI reasoning layer. Optional, cached, deduplicated, and can never break the terminal."""
from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from aiterm.ai.base import AIProvider, AIResult, AIUnavailable, parse_ai_json
from aiterm.ai.context import build_context
from aiterm.ai.providers import build_provider
from aiterm.core.config import AIConfig
from aiterm.core.models import Diagnostic

SYSTEM_PROMPT = """You are a debugging assistant inside a developer terminal.
The section 'DETECTED FACT' comes from a compiler/linter/runtime and is TRUE. Everything you add is INFERENCE.
Never invent files, APIs or line numbers that are not in the context. If unsure, lower confidence and set
requires_manual_review=true. Values shown as ******** are redacted secrets; never ask for them.
Reply with ONE JSON object only, keys:
problem (short), cause (why it happened), explanation (2-4 sentences), suggested_fix (short text or code),
fixed_line (the full corrected replacement for the reported line, single line, or null),
confidence (0..1), requires_manual_review (bool)."""


class AIEngine:
    def __init__(self, cfg: AIConfig, provider: Optional[AIProvider] = None, cache_size: int = 256):
        self.cfg = cfg
        self.provider = provider
        self.last_error = ""
        self._cache: "OrderedDict[str, AIResult]" = OrderedDict()
        self._size = cache_size

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.enabled)

    def explain(self, d: Diagnostic, root: Path, languages=()) -> Optional[AIResult]:
        """Return an AIResult, or None when AI is off/unavailable (caller shows local info)."""
        self.last_error = ""
        if not self.enabled:
            self.last_error = "AI disabled (set [ai] enabled = true)"
            return None
        ctx = build_context(d, root, self.cfg, languages)
        key = hashlib.sha1((self.cfg.provider + self.cfg.model + ctx.text).encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        try:
            if self.provider is None:
                self.provider = build_provider(self.cfg)
            raw = self.provider.complete(SYSTEM_PROMPT, ctx.text)
        except AIUnavailable as e:
            self.last_error = str(e)
            return None
        except Exception as e:  # provider bugs must not propagate
            self.last_error = f"AI provider error: {type(e).__name__}"
            return None
        res = parse_ai_json(raw, self.provider.name)
        self._cache[key] = res
        if len(self._cache) > self._size:
            self._cache.popitem(last=False)
        return res
