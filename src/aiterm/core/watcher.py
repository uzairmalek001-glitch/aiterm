"""File watching. inotify (via `watchdog`) when installed, incremental mtime polling otherwise."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable, Dict, Iterable, Set

from aiterm.analyzers.base import known_extensions

Callback = Callable[[Path], None]
TEMP_SUFFIXES = (".swp", ".swx", ".tmp", "~", ".pyc", ".class", ".o")


def is_relevant(path: Path, root: Path, ignore_dirs: Iterable[str], exts: Iterable[str] = ()) -> bool:
    exts = tuple(exts) or tuple(known_extensions())
    name = path.name
    if name.startswith(".#") or name.endswith(TEMP_SUFFIXES) or name.startswith("4913"):
        return False
    if path.suffix not in exts:
        return False
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    ignore = set(ignore_dirs)
    return not any(p in ignore for p in parts[:-1])


class PollingWatcher:
    """Stat-only polling: cheap, dependency-free, and only *changed* files reach analysis."""

    def __init__(self, root: Path, ignore_dirs, callback: Callback, interval: float = 1.0):
        self.root, self.ignore, self.callback, self.interval = Path(root), set(ignore_dirs), callback, interval
        self._stop = threading.Event()
        self._thread = None
        self._state: Dict[str, int] = {}

    def scan(self) -> Dict[str, int]:
        exts = tuple(known_extensions())
        out: Dict[str, int] = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in self.ignore]
            for fn in filenames:
                p = Path(dirpath, fn)
                if is_relevant(p, self.root, self.ignore, exts):
                    try:
                        out[str(p)] = p.stat().st_mtime_ns
                    except OSError:
                        pass
        return out

    def poll_once(self) -> Set[str]:
        new = self.scan()
        changed = {p for p, m in new.items() if self._state.get(p) != m}
        self._state = new
        return changed

    def start(self, initial_scan_silent: bool = True) -> None:
        if initial_scan_silent:
            self._state = self.scan()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="aiterm-poll")
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                for p in self.poll_once():
                    self.callback(Path(p))
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()


class WatchdogWatcher:
    """Event-driven (Linux inotify) watcher. Requires `pip install aiterm[watch]`."""

    def __init__(self, root: Path, ignore_dirs, callback: Callback):
        self.root, self.ignore, self.callback = Path(root), set(ignore_dirs), callback
        self._observer = None

    def start(self) -> None:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        outer = self

        class Handler(FileSystemEventHandler):
            def _maybe(self, p):
                p = Path(p)
                if is_relevant(p, outer.root, outer.ignore):
                    outer.callback(p)

            def on_modified(self, e):
                if not e.is_directory:
                    self._maybe(e.src_path)

            def on_created(self, e):
                if not e.is_directory:
                    self._maybe(e.src_path)

            def on_moved(self, e):  # editors save via rename
                if not e.is_directory:
                    self._maybe(e.dest_path)

        self._observer = Observer()
        self._observer.schedule(Handler(), str(self.root), recursive=True)
        self._observer.daemon = True
        self._observer.start()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()


def make_watcher(root: Path, ignore_dirs, callback: Callback, backend: str = "auto", interval: float = 1.0):
    if backend in ("auto", "watchdog"):
        try:
            import watchdog  # noqa: F401
            return WatchdogWatcher(root, ignore_dirs, callback)
        except ImportError:
            if backend == "watchdog":
                raise
    return PollingWatcher(root, ignore_dirs, callback, interval)
