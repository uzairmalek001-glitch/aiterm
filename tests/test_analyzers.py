import shutil
import unittest
from helpers import *  # noqa
from aiterm.analyzers.base import all_analyzers, get_analyzer
from aiterm.analyzers.classify import classify
from aiterm.analyzers.parsers import parse_gcc_style, parse_tsc, parse_node_check
from aiterm.core.engine import DiagnosticEngine
from aiterm.core.models import Diagnostic


class Registry(unittest.TestCase):
    def test_all_languages_registered(self):
        names = {a.name for a in all_analyzers()}
        self.assertEqual(names, {"python", "javascript", "typescript", "c", "cpp", "java", "kotlin", "rust"})

    def test_extension_dispatch(self):
        from pathlib import Path
        for ext, name in [(".py", "python"), (".ts", "typescript"), (".rs", "rust"), (".kt", "kotlin"), (".cc", "cpp")]:
            self.assertEqual(get_analyzer(Path("x" + ext)).name, name)


class PythonTests(unittest.TestCase):
    def setUp(self):
        self.root = tmpdir()
        self.eng = DiagnosticEngine(self.root, cfg())

    def test_missing_colon_spec_example(self):
        f = write(self.root, "calculator.py",
                  "def calculate_total(items):\n    total = 0\n    for item in items\n        total += item\n    return total\n")
        (d,) = self.eng.analyze_file(f)
        self.assertEqual((d.category, d.severity, d.line, d.file), ("SYNTAX_ERROR", "error", 3, "calculator.py"))
        self.assertEqual(d.fix_line, "    for item in items:")
        self.assertTrue(d.fingerprint and d.timestamp and d.id == d.fingerprint[:8])

    def test_clean_file(self):
        f = write(self.root, "ok.py", "import os\nprint(os.getcwd())\n")
        self.assertEqual(self.eng.analyze_file(f), [])

    def test_moved_class_import(self):
        write(self.root, "services/__init__.py", "")
        write(self.root, "services/user_service.py", "class UserService: pass\n")
        write(self.root, "users.py", "X = 1\n")
        f = write(self.root, "src/api.py", "from users import UserService\n")
        ds = self.eng.analyze_file(f)
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0].category, "IMPORT_ERROR")
        self.assertEqual(ds[0].fix_line, "from services.user_service import UserService")

    def test_missing_third_party_module_is_warning(self):
        f = write(self.root, "a.py", "import nonexistent_pkg_zzz\n")
        (d,) = self.eng.analyze_file(f)
        self.assertEqual((d.category, d.severity), ("IMPORT_ERROR", "warning"))

    def test_guarded_import_ignored(self):
        f = write(self.root, "a.py", "try:\n    import nonexistent_pkg_zzz\nexcept ImportError:\n    pass\n")
        self.assertEqual(self.eng.analyze_file(f), [])

    def test_local_modules_not_flagged(self):
        write(self.root, "helper.py", "def h(): pass\n")
        f = write(self.root, "a.py", "import helper\nfrom helper import h\n")
        self.assertEqual(self.eng.analyze_file(f), [])

    def test_deleted_file_clears_state(self):
        f = write(self.root, "a.py", "def (:\n")
        self.assertTrue(self.eng.analyze_file(f))
        f.unlink()
        self.eng.analyze_file(f)
        self.assertEqual(self.eng.all_current(), [])


class EngineBehaviour(unittest.TestCase):
    def test_cache_avoids_reanalysis(self):
        root = tmpdir()
        f = write(root, "a.py", "def (:\n")
        eng = DiagnosticEngine(root, cfg())
        eng.analyze_file(f)
        eng.analyze_file(f)
        eng.analyze_file(f)
        self.assertEqual(eng.analyses_run, 1)
        write(root, "a.py", "def (:\n\n")
        eng.analyze_file(f)
        self.assertEqual(eng.analyses_run, 2)

    def test_duplicate_suppression_and_cooldown(self):
        root = tmpdir()
        f = write(root, "a.py", "def (:\n")
        eng = DiagnosticEngine(root, cfg(cooldown_seconds=100))
        ds = eng.analyze_file(f)
        self.assertEqual(len(eng.fresh(ds, now=0)), 1)
        self.assertEqual(len(eng.fresh(ds, now=10)), 0)      # suppressed
        self.assertEqual(len(eng.fresh(ds, now=101)), 1)     # cooldown elapsed

    def test_resolved_then_reintroduced_notifies_again(self):
        root = tmpdir()
        f = write(root, "a.py", "def (:\n")
        eng = DiagnosticEngine(root, cfg(cooldown_seconds=1000))
        eng.fresh(eng.analyze_file(f), now=0)
        write(root, "a.py", "x = 1\n")
        eng.analyze_file(f)
        eng.forget_resolved()
        write(root, "a.py", "def (:\n")
        self.assertEqual(len(eng.fresh(eng.analyze_file(f), now=1)), 1)

    def test_ignore_messages(self):
        root = tmpdir()
        f = write(root, "a.py", "def (:\n")
        eng = DiagnosticEngine(root, cfg(ignore_messages=["invalid syntax"]))
        self.assertEqual(eng.analyze_file(f), [])

    def test_language_disabled(self):
        root = tmpdir()
        f = write(root, "a.py", "def (:\n")
        self.assertEqual(DiagnosticEngine(root, cfg(languages=["c"])).analyze_file(f), [])


class ParserTests(unittest.TestCase):
    def test_gcc(self):
        out = "/p/main.cpp:27:5: error: no matching function for call to 'foo(int, int, int)'\n" \
              "/p/main.cpp:3:6: note: candidate expects 2 arguments\n/p/main.cpp:9:1: warning: unused variable 'x'\n"
        ds = parse_gcc_style(out, "cpp", tmpdir())
        self.assertEqual([(d.line, d.severity) for d in ds], [(27, "error"), (9, "warning")])
        self.assertEqual(ds[0].category, "TYPE_ERROR")

    def test_rustc_short_and_javac_and_kotlin(self):
        r = tmpdir()
        self.assertEqual(parse_gcc_style("src/main.rs:3:5: error[E0425]: cannot find value `x`", "rust", r)[0].line, 3)
        self.assertEqual(parse_gcc_style("Main.java:7: error: cannot find symbol", "java", r)[0].line, 7)
        self.assertEqual(parse_gcc_style("a.kt:2:9: error: unresolved reference: foo", "kotlin", r)[0].column, 9)

    def test_tsc(self):
        (d,) = parse_tsc("src/a.ts(3,5): error TS1005: ';' expected.", tmpdir())
        self.assertEqual((d.line, d.column, d.category), (3, 5, "SYNTAX_ERROR"))

    def test_node(self):
        (d,) = parse_node_check("/x/a.js:2\n  return 1;\n  ^^^^^^\n\nSyntaxError: Unexpected token 'return'\n", tmpdir() / "a.js", tmpdir())
        self.assertEqual((d.line, d.category), (2, "SYNTAX_ERROR"))

    def test_classifier(self):
        self.assertEqual(classify("No module named 'x'").value, "IMPORT_ERROR")
        self.assertEqual(classify("mismatched types").value, "TYPE_ERROR")
        self.assertEqual(classify("hardcoded password").value, "SECURITY_WARNING")
        self.assertEqual(classify("???", default=__import__("aiterm.core.models", fromlist=["Category"]).Category.UNKNOWN).value, "UNKNOWN")

    def test_diagnostic_shape(self):
        d = Diagnostic("main.py", 42, 15, "error", "SYNTAX_ERROR", "m", "python")
        self.assertEqual(set(d.to_dict()) >= {"file", "line", "column", "severity", "category", "message", "source", "timestamp", "fingerprint"}, True)
        self.assertEqual(Diagnostic.from_dict(d.to_dict()).fingerprint, d.fingerprint)


@unittest.skipUnless(shutil.which("gcc"), "gcc not installed")
class RealCompiler(unittest.TestCase):
    def test_gcc_detects_error(self):
        root = tmpdir()
        f = write(root, "m.c", "int main(void){ return 0 }\n")
        ds = DiagnosticEngine(root, cfg()).analyze_file(f)
        self.assertTrue(ds and ds[0].category == "SYNTAX_ERROR")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RealNode(unittest.TestCase):
    def test_node_syntax(self):
        root = tmpdir()
        f = write(root, "a.js", "function f( {\n}\n")
        self.assertTrue(DiagnosticEngine(root, cfg()).analyze_file(f))


if __name__ == "__main__":
    unittest.main()
