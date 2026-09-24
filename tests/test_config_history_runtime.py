import json
import unittest
from helpers import *  # noqa
from aiterm.core.config import load_config, DEFAULT_TOML, Config
from aiterm.core.history import History
from aiterm.core.models import Diagnostic
from aiterm.core.project import detect_project
from aiterm.terminal.output_parser import parse_output


class ConfigTests(unittest.TestCase):
    def test_defaults_are_privacy_first(self):
        c = Config()
        self.assertFalse(c.ai.enabled)
        self.assertFalse(c.ai.auto)

    def test_load_and_merge(self):
        root = tmpdir()
        write(root, "aiterm.toml", '[ai]\nenabled = true\nprovider = "mock"\n[notifications]\nwarnings = false\n')
        c = load_config(root)
        self.assertTrue(c.ai.enabled)
        self.assertEqual(c.ai.provider, "mock")
        self.assertFalse(c.notifications.warnings)
        self.assertTrue(c.notifications.errors)       # untouched defaults survive

    def test_invalid_config_falls_back(self):
        root = tmpdir()
        write(root, "aiterm.toml", "this is [[[ not toml")
        c = load_config(root)
        self.assertFalse(c.ai.enabled)
        self.assertIn("INVALID", c.source_path)

    def test_default_toml_parses(self):
        import tomllib
        tomllib.loads(DEFAULT_TOML)


class HistoryTests(unittest.TestCase):
    def test_roundtrip_lookup_by_prefix(self):
        root = tmpdir()
        h = History(root)
        d = Diagnostic("a.py", 1, 0, "error", "SYNTAX_ERROR", "m", "python", fix_line="x")
        h.record(d)
        h.record_ai(d.id, {"problem": "p"})
        got = h.get(d.id[:4])
        self.assertEqual(got.fingerprint, d.fingerprint)
        self.assertEqual(h.entries()[0]["ai"], {"problem": "p"})

    def test_crash_recovery_corrupt_lines(self):
        root = tmpdir()
        h = History(root)
        d = Diagnostic("a.py", 1, 0, "error", "SYNTAX_ERROR", "m", "python")
        h.record(d)
        with h.path.open("a") as f:
            f.write('{"type": "diag", "id": "abc", "fi')    # torn write
        h.record(Diagnostic("b.py", 2, 0, "error", "SYNTAX_ERROR", "n", "python"))
        self.assertEqual(len(h.entries()), 2)

    def test_secrets_never_logged(self):
        root = tmpdir()
        h = History(root)
        h.record(Diagnostic("a.py", 1, 0, "error", "RUNTIME_ERROR", "bad password=hunter2hunter2", "python",
                            raw="token=abcdef123456"))
        txt = h.path.read_text()
        self.assertNotIn("hunter2hunter2", txt)
        self.assertNotIn("abcdef123456", txt)

    def test_missing_history(self):
        self.assertEqual(History(tmpdir()).entries(), [])
        self.assertIsNone(History(tmpdir()).get("zz"))


class ProjectTests(unittest.TestCase):
    def test_detect(self):
        root = tmpdir()
        write(root, "a.py", "")
        write(root, "b.py", "")
        write(root, "web/x.ts", "")
        write(root, "node_modules/y.js", "")
        write(root, "pyproject.toml", "")
        info = detect_project(root, ["node_modules"])
        self.assertEqual(info.languages, ["python", "typescript"])
        self.assertIn("pyproject.toml", info.markers)


class RuntimeOutput(unittest.TestCase):
    def test_python_traceback(self):
        root = tmpdir()
        write(root, "app.py", "x")
        tb = ('Traceback (most recent call last):\n  File "%s", line 7, in <module>\n    main()\n'
              '  File "/usr/lib/python3/site.py", line 1, in main\n    raise\nValueError: bad value\n' % (root / "app.py"))
        (d,) = parse_output(tb, root)
        self.assertEqual((d.file, d.line, d.category, d.message), ("app.py", 7, "RUNTIME_ERROR", "ValueError: bad value"))

    def test_import_error_traceback(self):
        root = tmpdir()
        tb = 'Traceback (most recent call last):\n  File "api.py", line 84, in <module>\n    from a import UserService\n' \
             "ImportError: cannot import name 'UserService' from 'a'\n"
        (d,) = parse_output(tb, root)
        self.assertEqual((d.category, d.line), ("IMPORT_ERROR", 84))

    def test_pytest_failure(self):
        (d,) = parse_output("FAILED tests/test_x.py::test_add - assert 3 == 4\n", tmpdir())
        self.assertEqual((d.category, d.file), ("TEST_FAILURE", "tests/test_x.py"))
        self.assertIn("test_add", d.message)

    def test_ansi_is_stripped_and_gcc_lines_parsed(self):
        (d,) = parse_output("\x1b[1mmain.cpp:27:5:\x1b[0m error: no matching function for call to 'foo'\n", tmpdir())
        self.assertEqual((d.file, d.line), ("main.cpp", 27))

    def test_rust_panic_and_node(self):
        r = tmpdir()
        write(r, "a.js", "")
        (p,) = parse_output("thread 'main' panicked at src/main.rs:4:5:\nindex out of bounds\n", r)
        self.assertEqual((p.line, p.category), (4, "RUNTIME_ERROR"))
        js = "TypeError: x is not a function\n    at run (%s:3:9)\n" % (r / "a.js")
        (n,) = parse_output(js, r)
        self.assertEqual((n.file, n.line), ("a.js", 3))

    def test_dedupe_and_noise(self):
        self.assertEqual(parse_output("hello world\nall good\n", tmpdir()), [])


if __name__ == "__main__":
    unittest.main()
