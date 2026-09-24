# Security & privacy
- **AI is opt-in** (`ai.enabled=false`). With it off, nothing leaves your machine. `provider="local"` keeps it local.
- **Minimal context only:** the diagnostic, ±N source lines, the enclosing function, import lines, and a short git diff
  of that one file. Never the repository.
- **Redaction before every request** (`security/redact.py`): private-key blocks, AWS/GitHub/Slack/Google/`sk-` keys, JWTs,
  Bearer tokens, URL credentials, and `NAME=value` where NAME contains key/secret/password/token/auth… → `********`.
- **Sensitive files are never read for AI:** `.env*`, `*.pem`, `*.key`, `id_*`, `.npmrc`, `.netrc`, `credentials*`,
  `*.tfvars`, … Files outside the project root are refused (path traversal).
- **Keys:** read from an environment variable named in config; sent in headers (not URLs); error messages never include them.
- **Logs/history/notifications** (`.aiterm/history.jsonl`, `.aiterm/notifications.log`, desktop popups, terminal boxes) are redacted, local-only, and there is no remote telemetry.
- **No silent edits:** patches are diffs; `apply()` requires `approved=True`, refuses stale files, backs up to `.aiterm/backups/`.
- **Limits:** regex redaction is best-effort — it can miss unusual secret formats. Keep `.aiterm/` out of git (`.gitignore`).
