"""Monitor: watcher -> debouncer -> engine -> (optional AI) -> notifications. Loosely coupled via injection."""
from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path
from typing import Optional, Set

from aiterm.ai.engine import AIEngine
from aiterm.core.config import Config
from aiterm.core.debounce import Debouncer
from aiterm.core.engine import DiagnosticEngine
from aiterm.core.history import History
from aiterm.core.watcher import make_watcher
from aiterm.notifications.manager import NotificationManager

log = logging.getLogger("aiterm")


class Monitor:
    def __init__(self, root: Path, cfg: Config, engine: DiagnosticEngine, notifier: NotificationManager,
                 ai: Optional[AIEngine] = None, history: Optional[History] = None, languages=()):
        self.root, self.cfg, self.engine, self.notifier = Path(root), cfg, engine, notifier
        self.ai, self.history, self.languages = ai, history, languages
        self._lock = threading.Lock()
        self.file_debounce = Debouncer(cfg.debounce_ms / 1000, self._on_files, cfg.max_wait_ms / 1000)
        self.out_debounce = Debouncer(0.5, self._on_output, 2.0)
        self._out_buf: list = []
        self.watcher = None
        self._ai_q: "queue.Queue" = queue.Queue()
        self._ai_thread: Optional[threading.Thread] = None

    # -- inputs --
    def start(self) -> None:
        self.watcher = make_watcher(self.root, self.cfg.ignore_dirs, self.file_debounce.push,
                                    self.cfg.watch_backend, self.cfg.poll_interval)
        self.watcher.start()

    def stop(self) -> None:
        if self.watcher:
            self.watcher.stop()
        self.file_debounce.close()
        self.out_debounce.close()
        self._ai_q.put(None)

    def wait_idle(self) -> None:
        """Block until queued AI work is finished (used by tests / one-shot commands)."""
        self._ai_q.join()

    def feed_output(self, text: str) -> None:
        with self._lock:
            self._out_buf.append(text)
            self._out_buf = self._out_buf[-400:]
        self.out_debounce.push("out")

    # -- pipeline --
    def _on_files(self, paths: Set[Path]) -> None:
        with self._lock:
            self._handle(self.engine.analyze_paths(paths))

    def _on_output(self, _items) -> None:
        with self._lock:
            text, self._out_buf = "".join(self._out_buf), []
            self._handle(self.engine.ingest_output(text))

    def process_output_now(self, text: str) -> int:
        with self._lock:
            return self._handle(self.engine.ingest_output(text))

    def process_files_now(self, paths) -> int:
        with self._lock:
            return self._handle(self.engine.analyze_paths(paths))

    def _handle(self, diags) -> int:
        """Notify immediately with local facts; AI enrichment is queued and never blocks monitoring."""
        try:
            fresh = self.engine.fresh(diags)
            items = []
            for d in fresh:
                if self.history:
                    self.history.record(d)
                items.append((d, None))
                if self._wants_ai(d):
                    self._enqueue_ai(d)
            n = self.notifier.notify(items) if items else 0
            self.engine.forget_resolved()
            return n
        except Exception as e:  # the monitor must survive anything
            log.exception("monitor error: %s", e)
            return 0

    def _wants_ai(self, d) -> bool:
        """AI only for what local tooling cannot already explain and fix (obvious errors skip it)."""
        a = self.ai
        return bool(a and a.enabled and a.cfg.auto and not d.fix_line and d.category in a.cfg.auto_categories)

    def _enqueue_ai(self, d) -> None:
        if self._ai_thread is None or not self._ai_thread.is_alive():
            self._ai_thread = threading.Thread(target=self._ai_worker, daemon=True, name="aiterm-ai")
            self._ai_thread.start()
        self._ai_q.put(d)

    def _ai_worker(self) -> None:
        while True:
            d = self._ai_q.get()
            try:
                if d is None:
                    return
                res = self.ai.explain(d, self.root, self.languages)   # slow network call: no locks held
                if res:
                    if self.history:
                        self.history.record_ai(d.id, res.to_dict())
                    self.notifier.notify([(d, res)])                  # follow-up with AI analysis
            except Exception as e:
                log.warning("AI worker error: %s", type(e).__name__)
            finally:
                self._ai_q.task_done()
