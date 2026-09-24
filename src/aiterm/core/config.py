"""Configuration (TOML, stdlib only). Search order: project ./aiterm.toml, ~/.config/aiterm/config.toml."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Optional

ALL_LANGUAGES = ["python", "javascript", "typescript", "c", "cpp", "java", "kotlin", "rust"]
DEFAULT_IGNORE = [".git", "node_modules", "__pycache__", ".venv", "venv", "target", "build",
                  "dist", ".aiterm", ".mypy_cache", ".pytest_cache", ".idea", ".gradle"]


@dataclass
class AIConfig:
    enabled: bool = False              # privacy-first: cloud AI is opt-in
    provider: str = "gemini"           # gemini | openai | local | mock
    model: str = ""
    temperature: float = 0.1
    timeout: float = 20.0
    api_key_env: str = ""              # NAME of the env var holding the key (never the key)
    base_url: str = ""                 # for local / OpenAI-compatible servers
    auto: bool = False                 # explain automatically (else on demand)
    auto_categories: list = field(default_factory=lambda: ["RUNTIME_ERROR", "TEST_FAILURE", "TYPE_ERROR", "UNKNOWN", "LOGIC_WARNING"])
    context_lines: int = 12
    max_context_chars: int = 6000


@dataclass
class NotifyConfig:
    errors: bool = True
    warnings: bool = True
    style: bool = False
    performance: bool = False
    terminal: bool = True
    desktop: bool = True
    max_per_batch: int = 5


@dataclass
class Config:
    debounce_ms: int = 400
    max_wait_ms: int = 3000
    cooldown_seconds: int = 300
    poll_interval: float = 1.0
    watch_backend: str = "auto"        # auto | watchdog | polling
    languages: list = field(default_factory=lambda: list(ALL_LANGUAGES))
    ignore_dirs: list = field(default_factory=lambda: list(DEFAULT_IGNORE))
    ignore_messages: list = field(default_factory=list)
    use_linters: bool = True
    ai: AIConfig = field(default_factory=AIConfig)
    notifications: NotifyConfig = field(default_factory=NotifyConfig)
    source_path: Optional[str] = None


def _merge(obj, data: dict) -> None:
    for f in fields(obj):
        if f.name not in data:
            continue
        cur = getattr(obj, f.name)
        if is_dataclass(cur) and isinstance(data[f.name], dict):
            _merge(cur, data[f.name])
        else:
            setattr(obj, f.name, data[f.name])


def load_config(root: Optional[Path] = None, path: Optional[Path] = None) -> Config:
    cfg = Config()
    candidates = [path] if path else []
    if root:
        candidates.append(Path(root) / "aiterm.toml")
    candidates.append(Path.home() / ".config" / "aiterm" / "config.toml")
    for c in candidates:
        if c and Path(c).is_file():
            try:
                _merge(cfg, tomllib.loads(Path(c).read_text(encoding="utf-8")))
                cfg.source_path = str(c)
            except (tomllib.TOMLDecodeError, OSError):
                # A broken config must never crash the terminal: fall back to defaults.
                cfg = Config()
                cfg.source_path = f"{c} (INVALID - using defaults)"
            break
    return cfg


DEFAULT_TOML = '''# aiterm configuration
debounce_ms = 400          # quiet period after the last change before analysing
max_wait_ms = 3000         # analyse at least this often while typing continues
cooldown_seconds = 300     # do not re-notify the same problem within this window
watch_backend = "auto"     # auto | watchdog (inotify) | polling
languages = ["python", "javascript", "typescript", "c", "cpp", "java", "kotlin", "rust"]
use_linters = true         # use ruff etc. when installed

[ai]
enabled = false            # set true to allow AI explanations (redacted context only)
provider = "gemini"        # gemini | openai | local | mock
model = ""                 # e.g. a Gemini/OpenAI model id, or an Ollama model
temperature = 0.1
api_key_env = "GEMINI_API_KEY"   # env var NAME; never put the key in this file
auto = false               # false = explain on demand (Explain button / `aiterm explain`)

[notifications]
errors = true
warnings = true
style = false
performance = false
terminal = true
desktop = true
max_per_batch = 5
'''
