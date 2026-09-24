# AI provider setup
```toml
[ai]
enabled = true
provider = "gemini"          # or openai | local | mock
model = "<a model id you have access to>"
api_key_env = "GEMINI_API_KEY"
```
- **Gemini:** `export GEMINI_API_KEY=...` (Generative Language API, `generateContent`).
- **OpenAI / compatible:** `export OPENAI_API_KEY=...`; set `base_url` for compatible servers.
- **Local (Ollama):** `provider="local"`, `model="<pulled model>"`, default `base_url=http://127.0.0.1:11434`.
- **Mock:** deterministic, offline; for tests/demos.
New provider: subclass `AIProvider.complete(system, user) -> str`, raise `AIUnavailable` on failure, add to `PROVIDERS`.
The provider must return JSON: `problem, cause, explanation, suggested_fix, fixed_line, confidence, requires_manual_review`
(non-conforming replies are kept as text and flagged for manual review). Provider adapters were written from the public
API shapes and unit-tested with mocks; verify against your account with `aiterm analyze --ai`.
