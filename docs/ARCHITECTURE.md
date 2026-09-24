# Architecture
```
Terminal Engine (terminal/shell.py)  ──output tap──┐
File Watcher (core/watcher.py) → Debouncer ────────┤
                                                   ▼
                       Monitor (core/monitor.py) — orchestration only
                                                   │
  Project Detector ─ Language Analyzers ─ Diagnostic Engine (cache, dedupe, cooldown) ─ Error Classifier/Correlator
                                                   │  Diagnostic (core/models.py)
                       History (JSONL) ◄───────────┤
                                                   ├─► AI Engine: Context Builder → Redaction → Provider (optional)
                                                   ▼
                       Notification Manager (terminal / desktop / file sinks) ─ Patch Manager (explicit approval)
```
- **Loose coupling:** `Monitor` receives engine, notifier, AI and history by injection; each is testable alone.
- **Analyzers:** `LanguageAnalyzer.analyze(path, root) -> [Diagnostic]`, registered via `@register`; the core never
  names a language.
- **Efficiency:** events → `Debouncer` (quiet period + max-wait) → only changed files → content-hash cache → fingerprint
  dedupe with cooldown → AI cache keyed by redacted context hash. Idle cost is zero with watchdog, one stat-walk/second with polling.
- **Correlation:** Python import failures search the project for the moved definition; runtime traces are mapped
  to in-project frames; the same problem seen by compiler and runtime dedupes by fingerprint (file:line:category:message).
- **Failure isolation:** analyzer exceptions, sink exceptions, provider errors, corrupt history/config are all contained.
