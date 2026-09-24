"""Runs aiterm against examples/stress_project (2000+ lines, 65 files, one intentional mistake each)."""
import json
import shutil
import subprocess
import sys
import unittest
from helpers import *  # noqa
from aiterm.core.engine import DiagnosticEngine
from aiterm.terminal.output_parser import parse_output

STRESS = ROOT / "examples" / "stress_project"
MANIFEST = json.loads((STRESS / "MANIFEST.json").read_text())
TOOL = {"c": "gcc", "js": "node", "ts": "tsc"}


def needs_tool(rel):
    t = TOOL.get(rel.split("/")[0])
    if rel.endswith(".cpp"):
        t = "g++"
    return t and not shutil.which(t)


class StressProject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eng = DiagnosticEngine(STRESS, cfg())

    def test_corpus_is_large(self):
        total = sum(len(p.read_text().splitlines()) for p in STRESS.rglob("*") if p.suffix in (".py", ".c", ".cpp", ".js", ".ts"))
        self.assertGreaterEqual(total, 1000)

    def test_every_static_mistake_detected_and_classified(self):
        failures = []
        for rel, m in MANIFEST.items():
            if m["mode"] != "static" or needs_tool(rel):
                continue
            ds = [d for d in self.eng.analyze_file(STRESS / rel) if d.severity in ("error", "warning")]
            cats = {d.category for d in ds}
            if m["expect"] not in cats:
                failures.append((rel, m["expect"], sorted(cats)))
            if "line" in m and not any(d.line == m["line"] for d in ds):
                failures.append((rel, "line", m["line"], [d.line for d in ds]))
        self.assertEqual(failures, [])

    def test_every_runtime_crash_detected(self):
        failures = []
        for rel, m in MANIFEST.items():
            if m["mode"] != "runtime":
                continue
            p = subprocess.run([sys.executable, rel], cwd=STRESS, capture_output=True, text=True)
            ds = parse_output(p.stderr, STRESS)
            if not (ds and m["expect"] in ds[0].message and ds[0].file == rel):
                failures.append((rel, m["expect"], [d.message for d in ds]))
        self.assertEqual(failures, [])

    def test_syntax_fixes_offered_for_missing_colon(self):
        for rel in ("syntax/missing_colon_for.py", "syntax/missing_colon_if.py", "syntax/missing_colon_def.py",
                    "syntax/missing_colon_class.py", "syntax/missing_colon_while.py"):
            (d,) = self.eng.analyze_file(STRESS / rel)
            self.assertTrue(d.fix_line and d.fix_line.endswith(":"), rel)


if __name__ == "__main__":
    unittest.main()
