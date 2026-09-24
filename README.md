# aiterm — a code-aware terminal

A real interactive shell (PTY) plus a background monitor that watches your project, runs **deterministic** tooling
(compilers, linters, `ast`, test output), and pops up a short, structured notification when something breaks.
AI is an *optional explanation layer* on top — never the detector, never required, never a single point of failure.

```
file change → debounce → project/language → local diagnostics → classify → (context+redact → AI?) → notification
```

## Install
```bash
pip install -e .            # stdlib-only core, Python 3.11+
pip install -e ".[watch]"   # + inotify events via watchdog (otherwise cheap mtime polling)
pip install -e ".[dev]"     # + pytest, ruff
aiterm doctor               # what's available on this machine
```

## Quick start with Gemini (AI is off until you enable it)
```bash
export GEMINI_API_KEY=...            # never put the key in a file
aiterm config --init                 # writes aiterm.toml
# edit aiterm.toml:  [ai] enabled = true,  provider = "gemini",  model = "<your model id>"
aiterm doctor                        # confirms the key is visible and AI is enabled
aiterm analyze --ai                  # or: aiterm explain <id>;  set auto = true for background explanations
```
AI calls run on a background worker: you always get the local notification first, and an AI follow-up when it arrives.

## Use
| Command | What it does |
|---|---|
| `aiterm` / `aiterm start` | Your `$SHELL` in a PTY + live monitoring (output tapped for tracebacks/compiler errors) |
| `aiterm watch` | Monitoring only; prints notification boxes |
| `aiterm analyze [path] [--json] [--ai]` | One-shot analysis (exit code 1 on errors, CI-friendly) |
| `aiterm run -- <cmd>` | Run a command and analyse its output (tracebacks, gcc/rustc/tsc, pytest failures) |
| `aiterm history` | Recent problems and their ids |
| `aiterm explain <id>` | Local hint, plus AI analysis if enabled |
| `aiterm fix <id>` | Show a unified diff; applies **only** after you type `y`; makes a backup |
| `aiterm config [--init]` | Show effective config / write `aiterm.toml` |
| `aiterm doctor` | Toolchain, watcher, notify-send, AI key checks |

Try it: `cd examples/broken_python && aiterm analyze` (missing colon, a moved class import, a missing package).

## What's deterministic vs. AI
Detected facts (file, line, message, category, fingerprint) always come from tools. AI output is shown under
"AI analysis (inference, confidence …)" and stored separately. AI is skipped when a local fix exists, and is
on-demand by default (`ai.auto = false`).

## Languages
Python (`ast` + import resolution + optional `ruff`), JavaScript (`node --check`), TypeScript (`tsc`), C (`gcc`),
C++ (`g++`), Java (`javac`), Kotlin (`kotlinc`), Rust (`cargo check` / `rustc`). A missing compiler simply disables
that analyzer (see `aiterm doctor`). Add a language: subclass `LanguageAnalyzer`, decorate with `@register`
(see `analyzers/tools.py`, ~6 lines).

## Docs
[Architecture](docs/ARCHITECTURE.md) · [Configuration](docs/CONFIGURATION.md) · [Security & privacy](docs/SECURITY.md) ·
[AI providers](docs/AI_PROVIDERS.md) · [Troubleshooting](docs/TROUBLESHOOTING.md)

## Tests
`pytest -q` or `cd tests && python -m unittest discover` (97 tests: debouncing, watching, parsers, redaction, AI
context, providers, outages, patches, history crash-recovery, and end-to-end runs on broken example projects).

## Known limitations (v0.1)
- Desktop popups use `notify-send` (Linux only). On other OSes you get terminal notifications and the log file.
- TypeScript with a `tsconfig.json` runs `tsc --noEmit -p` for the whole project and Rust runs `cargo check`; on large
  projects this is heavy (the debouncer and content-hash cache limit repeats). Incremental/project-level analysis is future work.
- Config is TOML (stdlib) rather than YAML to keep zero dependencies.
- Interactive PTY shell and `WatchdogWatcher` need manual testing on your machine; automated tests cover the polling
  watcher, the output parser, and the monitor pipeline.
- Notifications inside `aiterm start` are written to stderr / desktop, not a full-screen TUI panel yet.
- Automatic patches are single-line replacements (deterministic or AI `fixed_line`); multi-line AI patches are shown as text.
- Java/Kotlin/Rust analyzers are implemented and parser-tested but were not run against real toolchains here.
