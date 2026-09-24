import time
import unittest
from helpers import *  # noqa
from aiterm.core.debounce import Debouncer
from aiterm.core.watcher import PollingWatcher, is_relevant


class DebounceTests(unittest.TestCase):
    def test_burst_becomes_one_call(self):
        calls = []
        d = Debouncer(0.08, lambda items: calls.append(set(items)))
        for i in range(10):
            d.push("a.py")
            time.sleep(0.01)
        time.sleep(0.3)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], {"a.py"})

    def test_batches_multiple_files(self):
        calls = []
        d = Debouncer(0.05, lambda items: calls.append(set(items)))
        for n in ("a", "b", "c", "a"):
            d.push(n)
        time.sleep(0.25)
        self.assertEqual(calls, [{"a", "b", "c"}])

    def test_max_wait_forces_progress(self):
        calls = []
        d = Debouncer(0.2, lambda items: calls.append(1), max_wait=0.3)
        end = time.time() + 0.8
        while time.time() < end:
            d.push("x")
            time.sleep(0.05)
        self.assertGreaterEqual(len(calls), 1)  # kept typing, still analysed

    def test_callback_exception_is_contained(self):
        def boom(_): raise RuntimeError("x")
        d = Debouncer(0.02, boom)
        d.push(1)
        time.sleep(0.1)
        d.push(2)  # still usable
        d.flush()

    def test_flush(self):
        calls = []
        d = Debouncer(5, lambda i: calls.append(i))
        d.push(1)
        d.flush()
        self.assertEqual(calls, [{1}])


class WatcherTests(unittest.TestCase):
    def test_relevance_filter(self):
        root = tmpdir()
        ign = [".git", "node_modules"]
        self.assertTrue(is_relevant(root / "a.py", root, ign))
        self.assertFalse(is_relevant(root / "a.txt", root, ign))
        self.assertFalse(is_relevant(root / "node_modules" / "x.js", root, ign))
        self.assertFalse(is_relevant(root / ".a.py.swp", root, ign))
        self.assertFalse(is_relevant(root / ".#a.py", root, ign))

    def test_polling_detects_only_changes(self):
        root = tmpdir()
        write(root, "a.py", "x=1\n")
        write(root, "b.py", "y=1\n")
        w = PollingWatcher(root, [".git"], lambda p: None)
        w._state = w.scan()
        self.assertEqual(w.poll_once(), set())          # nothing changed -> nothing reported
        time.sleep(0.01)
        write(root, "a.py", "x=2\n")
        write(root, "c.py", "z=1\n")
        self.assertEqual({p.split("/")[-1] for p in w.poll_once()}, {"a.py", "c.py"})
        self.assertEqual(w.poll_once(), set())

    def test_polling_thread_delivers(self):
        root = tmpdir()
        write(root, "a.py", "x=1\n")
        got = []
        w = PollingWatcher(root, [], got.append, interval=0.05)
        w.start()
        time.sleep(0.1)
        write(root, "a.py", "x=22\n")
        time.sleep(0.4)
        w.stop()
        self.assertTrue(any(p.name == "a.py" for p in got))


if __name__ == "__main__":
    unittest.main()
