"""Debouncer: 10 keystrokes -> 10 file events -> ONE analysis."""
from __future__ import annotations

import threading
import time
from typing import Callable, Hashable, Optional, Set


class Debouncer:
    def __init__(self, delay: float, callback: Callable[[Set], None], max_wait: Optional[float] = None):
        self.delay, self.callback, self.max_wait = delay, callback, max_wait
        self._items: Set[Hashable] = set()
        self._timer: Optional[threading.Timer] = None
        self._first = 0.0
        self._lock = threading.Lock()
        self._closed = False

    def push(self, item: Hashable) -> None:
        with self._lock:
            if self._closed:
                return
            now = time.monotonic()
            if not self._items:
                self._first = now
            self._items.add(item)
            if self._timer:
                self._timer.cancel()
            wait = self.delay
            if self.max_wait is not None:
                wait = max(0.0, min(wait, self._first + self.max_wait - now))
            self._timer = threading.Timer(wait, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            items, self._items = self._items, set()
            self._timer = None
        if items:
            try:
                self.callback(items)
            except Exception:  # never let a callback kill the timer machinery
                pass

    def flush(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
        self._fire()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._timer:
                self._timer.cancel()
