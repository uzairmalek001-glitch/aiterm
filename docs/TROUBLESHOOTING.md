# Troubleshooting
- **Nothing is detected:** run `aiterm doctor`. A missing compiler (gcc, tsc, javac…) disables that language silently.
- **False "No module named X" for Python:** aiterm checks the environment it runs in. Install aiterm in your project's
  venv, or add the message to `ignore_messages`.
- **No desktop popups:** install `libnotify-bin` (`notify-send`) and run inside a desktop session, or use terminal output.
- **High CPU on huge repos:** `pip install aiterm[watch]` (inotify), add big folders to `ignore_dirs`, raise `poll_interval`.
- **"AI unavailable":** the message says why (key env not set, HTTP 401/403, timeout). Local diagnostics keep working.
- **Same error keeps reappearing:** raise `cooldown_seconds`, or add to `ignore_messages`.
- **Reset state:** delete `.aiterm/` (history, backups, notification log).
