"""End-to-end tests against intentionally broken example projects."""
import io
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock
from helpers import *  # noqa
from aiterm.ai.engine import AIEngine
from aiterm.ai.providers import MockProvider
from aiterm.cli.main import main
from aiterm.core.config import AIConfig
from aiterm.core.engine import DiagnosticEngine
from aiterm.core.history import History
from aiterm.core.monitor import Monitor
from aiterm.notifications.manager import ListSink, NotificationManager


def cli(*args, cwd, stdin=None):
    buf = io.StringIO()
    old = os.getcwd()
    os.chdir(cwd)
    try:
        with redirect_stdout(buf):
            if stdin is not None:
                with mock.patch("builtins.input", return_value=stdin):
                    rc = main(list(args))
            else:
                rc = main(list(args))
    finally:
        os.chdir(old)
    return rc, buf.getvalue()


def make_monitor(root, ai=None, **cfgkw):
    c = cfg(debounce_ms=50, max_wait_ms=300, **cfgkw)
    sink = ListSink()
    eng = DiagnosticEngine(root, c)
    return Monitor(root, c, eng, NotificationManager(c.notifications, [sink]), ai, History(root)), sink


class BrokenPythonProject(unittest.TestCase):
    def setUp(self):
        self.root = copy_example("broken_python")

    def test_cli_analyze_json(self):
        rc, out = cli("analyze", "--json", cwd=self.root)
        data = json.loads(out)
        self.assertEqual(rc, 1)
        cats = {(d["file"], d["category"]) for d in data}
        self.assertIn(("calculator.py", "SYNTAX_ERROR"), cats)
        self.assertIn(("api.py", "IMPORT_ERROR"), cats)

    def test_explain_without_ai_degrades(self):
        _, out = cli("analyze", "--json", cwd=self.root)
        calc = next(d for d in json.loads(out) if d["file"] == "calculator.py")
        rc, out = cli("explain", calc["id"], cwd=self.root)
        self.assertEqual(rc, 0)
        self.assertIn("Local diagnostics remain active", out)
        self.assertIn("calculator.py", out)

    def test_fix_reject_leaves_file_untouched(self):
        _, out = cli("analyze", "--json", cwd=self.root)
        calc = next(d for d in json.loads(out) if d["file"] == "calculator.py")
        before = (self.root / "calculator.py").read_text()
        with mock.patch("sys.stdin.isatty", return_value=True):
            rc, out = cli("fix", calc["id"], cwd=self.root, stdin="n")
        self.assertIn("No files were modified", out)
        self.assertEqual((self.root / "calculator.py").read_text(), before)

    def test_fix_apply_then_clean(self):
        _, out = cli("analyze", "--json", cwd=self.root)
        calc = next(d for d in json.loads(out) if d["file"] == "calculator.py")
        with mock.patch("sys.stdin.isatty", return_value=True):
            rc, out = cli("fix", calc["id"], cwd=self.root, stdin="y")
        self.assertIn("no problems remain", out)
        self.assertIn("items:\n", (self.root / "calculator.py").read_text())

    def test_fix_import_uses_project_knowledge(self):
        _, out = cli("analyze", "--json", cwd=self.root)
        imp = next(d for d in json.loads(out) if d["message"].startswith("cannot import name"))
        with mock.patch("sys.stdin.isatty", return_value=True):
            cli("fix", imp["id"], cwd=self.root, stdin="y")
        self.assertIn("from services.user_service import UserService", (self.root / "api.py").read_text())

    def test_history_and_doctor_and_config(self):
        cli("analyze", cwd=self.root)
        rc, out = cli("history", cwd=self.root)
        self.assertIn("calculator.py", out)
        self.assertEqual(cli("doctor", cwd=self.root)[0], 0)
        self.assertEqual(cli("config", "--init", cwd=self.root)[0], 0)
        self.assertEqual(cli("config", "--init", cwd=self.root)[0], 1)   # never overwrites
        self.assertIn('"enabled": false', cli("config", cwd=self.root)[1])

    def test_ai_explain_with_mock_provider(self):
        (self.root / "aiterm.toml").write_text('[ai]\nenabled = true\nprovider = "mock"\n')
        _, out = cli("analyze", "--json", cwd=self.root)
        calc = next(d for d in json.loads(out) if d["file"] == "calculator.py")
        rc, out = cli("explain", calc["id"], cwd=self.root)
        self.assertIn("inference", out)


class LiveMonitoring(unittest.TestCase):
    def test_edit_burst_triggers_one_analysis_and_one_notification(self):
        root = tmpdir()
        f = write(root, "calc.py", "x = 1\n")
        mon, sink = make_monitor(root)
        mon.start()
        try:
            time.sleep(0.2)
            for i in range(10):                       # 10 "keystrokes"
                f.write_text("def f(items):\n    for i in items\n" + " " * i)
                time.sleep(0.005)
            time.sleep(2.5)
        finally:
            mon.stop()
        self.assertGreaterEqual(len(sink.sent), 1)
        self.assertLessEqual(mon.engine.analyses_run, 3)   # not 10
        self.assertEqual(sink.sent[0][0].category, "SYNTAX_ERROR")

    def test_same_error_not_renotified_until_fixed(self):
        root = tmpdir()
        f = write(root, "a.py", "def (:\n")
        mon, sink = make_monitor(root)
        mon.process_files_now([f])
        mon.process_files_now([f])
        self.assertEqual(len(sink.sent), 1)
        f.write_text("x = 1\n")
        mon.process_files_now([f])
        f.write_text("def (:\n")
        mon.process_files_now([f])
        self.assertEqual(len(sink.sent), 2)

    def test_runtime_output_pipeline(self):
        root = copy_example("broken_python")
        mon, sink = make_monitor(root)
        p = subprocess.run([sys.executable, "crash.py"], cwd=root, capture_output=True, text=True)
        mon.process_output_now(p.stderr)
        self.assertEqual(sink.sent[0][0].category, "RUNTIME_ERROR")
        self.assertIn("ZeroDivisionError", sink.sent[0][0].message)

    def test_ai_only_for_non_obvious_and_survives_outage(self):
        root = copy_example("broken_python")
        prov = MockProvider()
        ai = AIEngine(AIConfig(enabled=True, auto=True), prov)
        mon, sink = make_monitor(root, ai=ai)
        mon.process_files_now([root / "calculator.py"])           # obvious + local fix -> no AI call
        self.assertEqual(prov.calls, 0)
        p = subprocess.run([sys.executable, "crash.py"], cwd=root, capture_output=True, text=True)
        mon.process_output_now(p.stderr)                          # runtime error -> AI used
        mon.wait_idle()
        self.assertEqual(prov.calls, 1)
        self.assertIsNone(sink.sent[0][1])                        # local notice came first
        self.assertIsNotNone(sink.sent[-1][1])                    # AI follow-up

        from aiterm.ai.base import AIProvider, AIUnavailable
        class Down(AIProvider):
            name = "down"
            def complete(self, s, u): raise AIUnavailable("offline")
        mon2, sink2 = make_monitor(root, ai=AIEngine(AIConfig(enabled=True, auto=True), Down()))
        mon2.process_output_now(p.stderr)
        mon2.wait_idle()
        self.assertEqual(len(sink2.sent), 1)                      # still notified, without AI
        self.assertIsNone(sink2.sent[0][1])

    def test_slow_ai_does_not_block_monitoring(self):
        from aiterm.ai.base import AIProvider
        class Slow(AIProvider):
            name = "slow"
            def complete(self, s, u):
                time.sleep(1.0)
                return "{}"
        root = copy_example("broken_python")
        mon, sink = make_monitor(root, ai=AIEngine(AIConfig(enabled=True, auto=True), Slow()))
        p = subprocess.run([sys.executable, "crash.py"], cwd=root, capture_output=True, text=True)
        t = time.monotonic()
        mon.process_output_now(p.stderr)
        self.assertLess(time.monotonic() - t, 0.5)                # returned while AI still running
        self.assertEqual(len(sink.sent), 1)
        # monitoring continues meanwhile
        f = write(root, "z.py", "def (:\n")
        mon.process_files_now([f])
        self.assertEqual(len(sink.sent), 2)
        mon.wait_idle()

    def test_analyzer_crash_does_not_stop_monitor(self):
        from aiterm.analyzers import base
        root = tmpdir()
        f = write(root, "a.py", "x=1\n")
        g = write(root, "b.py", "def (:\n")
        mon, sink = make_monitor(root)
        orig = base.get_analyzer(f).analyze
        calls = {"n": 0}
        def flaky(path, r):
            calls["n"] += 1
            if path.name == "a.py":
                raise RuntimeError("analyzer bug")
            return orig(path, r)
        with mock.patch.object(base.get_analyzer(f), "analyze", side_effect=flaky):
            mon.process_files_now([f, g])
        self.assertEqual(len(sink.sent), 1)

    def test_run_command_end_to_end(self):
        root = copy_example("broken_python")
        rc, out = cli("run", "--", sys.executable, "crash.py", cwd=root)
        self.assertNotEqual(rc, 0)


@unittest.skipUnless(shutil.which("gcc"), "gcc missing")
class BrokenC(unittest.TestCase):
    def test_c_project(self):
        root = copy_example("broken_c")
        rc, out = cli("analyze", "--json", cwd=root)
        cats = {d["category"] for d in json.loads(out)}
        self.assertTrue({"SYNTAX_ERROR", "TYPE_ERROR"} <= cats)


if __name__ == "__main__":
    unittest.main()
