import io
import unittest
from helpers import *  # noqa
from aiterm.ai.base import AIResult
from aiterm.core.config import NotifyConfig
from aiterm.core.models import Diagnostic
from aiterm.notifications.manager import NotificationManager, ListSink, TerminalSink, render_box
from aiterm.patches.manager import PatchManager, PatchError


def d(sev="error", cat="SYNTAX_ERROR", n=1):
    return Diagnostic("calculator.py", 3, 0, sev, cat, f"Expected ':' after the for statement {n}", "python",
                      fix_line="for item in items:")


class Notifications(unittest.TestCase):
    def test_box_contents(self):
        box = render_box(d())
        for s in ("AI Code Assistant", "calculator.py", "Line: 3", "for item in items:", "[Explain] [Fix] [Dismiss]"):
            self.assertIn(s, box)
        widths = {len(l) for l in box.splitlines()}
        self.assertEqual(len(widths), 1)  # tidy rectangle

    def test_ai_is_labelled_inference(self):
        box = render_box(d(), AIResult(cause="c", explanation="e", confidence=0.9, requires_manual_review=True))
        self.assertIn("inference", box)
        self.assertIn("manual review", box)

    def test_filters(self):
        sink = ListSink()
        m = NotificationManager(NotifyConfig(errors=True, warnings=False, style=False, performance=False), [sink])
        m.notify([(d("error"), None), (d("warning"), None), (d("info", "LINT_ERROR"), None),
                  (d("warning", "PERFORMANCE_WARNING"), None)])
        self.assertEqual([x[0].severity for x in sink.sent], ["error"])
        m2 = NotificationManager(NotifyConfig(warnings=True, performance=True), [sink := ListSink()])
        m2.notify([(d("warning"), None), (d("warning", "PERFORMANCE_WARNING"), None)])
        self.assertEqual(len(sink.sent), 2)

    def test_batching_collapses_overflow_and_orders_by_severity(self):
        sink = ListSink()
        m = NotificationManager(NotifyConfig(max_per_batch=2, warnings=True), [sink])
        items = [(d("warning", n=i), None) for i in range(5)] + [(d("critical", n=99), None)]
        m.notify(items)
        self.assertEqual(len(sink.sent), 2)
        self.assertEqual(sink.sent[0][0].severity, "critical")
        self.assertIn("+4 more", sink.summaries[0])

    def test_broken_sink_does_not_break_others(self):
        class Bad(ListSink):
            def send(self, *a): raise OSError("x")
        good = ListSink()
        NotificationManager(NotifyConfig(), [Bad(), good]).notify([(d(), None)])
        self.assertEqual(len(good.sent), 1)

    def test_file_and_desktop_sinks_redact(self):
        from aiterm.notifications.manager import FileSink
        root = tmpdir()
        bad = Diagnostic("a.py", 1, 0, "error", "RUNTIME_ERROR", "failed with password=hunter2hunter2 sk-" + "x" * 30,
                         "python-runtime", raw="token=abcdef123456")
        FileSink(root / "n.log").send(bad, None)
        txt = (root / "n.log").read_text()
        self.assertNotIn("hunter2hunter2", txt)
        self.assertNotIn("x" * 30, txt)
        self.assertNotIn("abcdef123456", txt)
        self.assertNotIn("hunter2hunter2", render_box(bad))

    def test_terminal_sink_writes(self):
        buf = io.StringIO()
        TerminalSink(buf).send(d(), None)
        self.assertIn("calculator.py", buf.getvalue())


class Patches(unittest.TestCase):
    def setUp(self):
        self.root = tmpdir()
        self.f = write(self.root, "calculator.py", "def t(items):\n    for item in items\n        pass\n")
        self.pm = PatchManager(self.root)

    def test_diff_is_standard_unified(self):
        p = self.pm.propose_line_fix("calculator.py", 2, "    for item in items:")
        self.assertIn("--- a/calculator.py", p.diff)
        self.assertIn("-    for item in items\n", p.diff)
        self.assertIn("+    for item in items:\n", p.diff)

    def test_propose_does_not_modify(self):
        before = self.f.read_text()
        self.pm.propose_line_fix("calculator.py", 2, "    for item in items:")
        self.assertEqual(self.f.read_text(), before)

    def test_apply_requires_explicit_approval(self):
        p = self.pm.propose_line_fix("calculator.py", 2, "    for item in items:")
        for bad in (False, None, 1, "yes"):
            with self.assertRaises(PatchError):
                self.pm.apply(p, approved=bad)
        self.assertNotIn("items:", self.f.read_text())

    def test_apply_with_backup(self):
        p = self.pm.propose_line_fix("calculator.py", 2, "    for item in items:")
        backup = self.pm.apply(p, approved=True)
        self.assertIn("items:\n", self.f.read_text())
        self.assertNotIn("items:", backup.read_text())
        self.pm.restore(backup, "calculator.py")
        self.assertNotIn("items:", self.f.read_text())

    def test_stale_patch_refused(self):
        p = self.pm.propose_line_fix("calculator.py", 2, "    for item in items:")
        self.f.write_text("changed = True\n")
        with self.assertRaises(PatchError):
            self.pm.apply(p, approved=True)
        self.assertEqual(self.f.read_text(), "changed = True\n")

    def test_indentation_restored_for_ai_fix(self):
        p = self.pm.propose_line_fix("calculator.py", 2, "for item in items:")
        self.assertIn("+    for item in items:", p.diff)

    def test_preserves_crlf_and_mode(self):
        import os
        f = write(self.root, "w.py", "a = 1\r\nb = (\r\n")
        os.chmod(f, 0o755)
        p = self.pm.propose_line_fix("w.py", 2, "b = 2")
        self.pm.apply(p, approved=True)
        self.assertEqual(f.read_bytes(), b"a = 1\r\nb = 2\r\n")
        self.assertEqual(os.stat(f).st_mode & 0o777, 0o755)

    def test_path_traversal_and_range(self):
        outside = write(tmpdir(), "x.py", "a\n")
        with self.assertRaises(PatchError):
            self.pm.propose_line_fix(str(outside), 1, "b")
        with self.assertRaises(PatchError):
            self.pm.propose_line_fix("calculator.py", 99, "b")


if __name__ == "__main__":
    unittest.main()
