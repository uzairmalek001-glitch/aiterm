# Configuration
Lookup: `./aiterm.toml` (project) → `~/.config/aiterm/config.toml`. `aiterm config --init` writes a commented file
(`config/aiterm.example.toml`). Invalid TOML never crashes aiterm; defaults are used and `doctor` shows it.

Top-level: `debounce_ms`, `max_wait_ms`, `cooldown_seconds`, `poll_interval`, `watch_backend` (auto|watchdog|polling),
`languages`, `ignore_dirs`, `ignore_messages` (substring match), `use_linters`.

`[notifications]`: `errors`, `warnings`, `style`, `performance`, `terminal`, `desktop`, `max_per_batch`.
Warnings/info are filtered by these switches; overflow beyond `max_per_batch` collapses to one line.

`[ai]`: `enabled` (default **false**), `provider` (gemini|openai|local|mock), `model`, `temperature`, `timeout`,
`api_key_env` (env var *name*), `base_url`, `auto`, `auto_categories`, `context_lines`, `max_context_chars`.
