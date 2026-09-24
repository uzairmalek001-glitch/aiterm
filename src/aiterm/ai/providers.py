"""Concrete providers (stdlib HTTP only). Keys come from env vars and are never logged."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from aiterm.ai.base import AIProvider, AIUnavailable
from aiterm.core.config import AIConfig


def _post(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise AIUnavailable(f"HTTP {e.code} from AI provider" + (" (check API key)" if e.code in (401, 403) else ""))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise AIUnavailable(f"AI provider unreachable: {type(e).__name__}")


def _key(cfg: AIConfig, default_env: str) -> str:
    env = cfg.api_key_env or default_env
    k = os.environ.get(env, "")
    if not k:
        raise AIUnavailable(f"API key env var {env} is not set")
    return k


class MockProvider(AIProvider):
    """Deterministic offline provider for tests/demos."""
    name = "mock"

    def __init__(self, cfg: AIConfig = None, reply: str = None):
        self.reply, self.calls = reply, 0

    def complete(self, system, user):
        self.calls += 1
        if self.reply is not None:
            return self.reply
        return json.dumps({"problem": "Mock analysis", "cause": "Mock cause (no real model was called)",
                           "explanation": "This is a deterministic offline response.", "suggested_fix": "",
                           "confidence": 0.5, "requires_manual_review": True})


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, cfg: AIConfig):
        self.cfg = cfg

    def complete(self, system, user):
        if not self.cfg.model:
            raise AIUnavailable("ai.model is not configured")
        base = self.cfg.base_url or "https://generativelanguage.googleapis.com"
        url = f"{base}/v1beta/models/{self.cfg.model}:generateContent"
        data = _post(url, {"systemInstruction": {"parts": [{"text": system}]},
                           "contents": [{"role": "user", "parts": [{"text": user}]}],
                           "generationConfig": {"temperature": self.cfg.temperature, "responseMimeType": "application/json"}},
                     {"x-goog-api-key": _key(self.cfg, "GEMINI_API_KEY")}, self.cfg.timeout)
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise AIUnavailable("unexpected response shape from Gemini")


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, cfg: AIConfig):
        self.cfg = cfg

    def complete(self, system, user):
        if not self.cfg.model:
            raise AIUnavailable("ai.model is not configured")
        base = (self.cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        data = _post(f"{base}/chat/completions",
                     {"model": self.cfg.model, "temperature": self.cfg.temperature,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                     {"Authorization": f"Bearer {_key(self.cfg, 'OPENAI_API_KEY')}"}, self.cfg.timeout)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise AIUnavailable("unexpected response shape from OpenAI-compatible API")


class LocalModelProvider(AIProvider):
    """Ollama-style local server: nothing leaves the machine."""
    name = "local"

    def __init__(self, cfg: AIConfig):
        self.cfg = cfg

    def complete(self, system, user):
        if not self.cfg.model:
            raise AIUnavailable("ai.model is not configured")
        base = (self.cfg.base_url or "http://127.0.0.1:11434").rstrip("/")
        data = _post(f"{base}/api/generate",
                     {"model": self.cfg.model, "system": system, "prompt": user, "stream": False, "format": "json",
                      "options": {"temperature": self.cfg.temperature}}, {}, self.cfg.timeout)
        if "response" not in data:
            raise AIUnavailable("unexpected response shape from local model server")
        return data["response"]


PROVIDERS = {"gemini": GeminiProvider, "openai": OpenAIProvider, "local": LocalModelProvider, "mock": MockProvider}


def build_provider(cfg: AIConfig) -> AIProvider:
    try:
        return PROVIDERS[cfg.provider](cfg)
    except KeyError:
        raise AIUnavailable(f"unknown AI provider '{cfg.provider}' (choose: {', '.join(PROVIDERS)})")
