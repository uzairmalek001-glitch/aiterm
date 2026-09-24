"""Regression: C/C++ diagnostics from gcc AND clang (e.g. Termux) must classify precisely."""
import unittest
from helpers import *  # noqa
from aiterm.analyzers.classify import classify
from aiterm.analyzers.parsers import parse_gcc_style
from aiterm.core.models import Category

GCC_UNTERMINATED = 'main.c:3:12: warning: missing terminating " character\nmain.c:3:12: error: missing terminating " character'
CLANG_UNTERMINATED = ("main.c:3:12: warning: missing terminating '\"' character [-Winvalid-pp-token]\n"
                      "main.c:3:12: error: expected expression\n"
                      "main.c:3:12: error: missing terminating '\"' character")
GCC_HEADER = "main.c:1:10: fatal error: not_a_real_header.h: No such file or directory"
CLANG_HEADER = "main.c:1:10: fatal error: 'not_a_real_header.h' file not found"


def cats(output, src="c"):
    return {d.category for d in parse_gcc_style(output, src, tmpdir())}


class UnterminatedString(unittest.TestCase):
    def test_gcc(self):
        self.assertEqual(cats(GCC_UNTERMINATED), {"SYNTAX_ERROR"})

    def test_clang(self):
        self.assertIn("SYNTAX_ERROR", cats(CLANG_UNTERMINATED))

    def test_message_level(self):
        self.assertEqual(classify("missing terminating \" character"), Category.SYNTAX_ERROR)
        self.assertEqual(classify("missing terminating '\"' character"), Category.SYNTAX_ERROR)


class MissingHeader(unittest.TestCase):
    def test_gcc(self):
        self.assertEqual(cats(GCC_HEADER), {"IMPORT_ERROR"})

    def test_clang(self):
        self.assertEqual(cats(CLANG_HEADER), {"IMPORT_ERROR"})

    def test_cpp_variants(self):
        self.assertEqual(cats(GCC_HEADER.replace("main.c", "main.cpp"), "cpp"), {"IMPORT_ERROR"})
        self.assertEqual(cats(CLANG_HEADER.replace("main.c", "main.cpp"), "cpp"), {"IMPORT_ERROR"})


class GenuineCompilationErrorsStayGeneric(unittest.TestCase):
    def test_still_compilation_error(self):
        for msg in ["'y' undeclared (first use in this function)",          # gcc
                    "use of undeclared identifier 'y'",                     # clang
                    "implicit declaration of function 'foo'",
                    "conflicting types for 'bar'",
                    "undefined reference to `missing_function'"]:
            self.assertEqual(classify(msg), Category.COMPILATION_ERROR, msg)

    def test_other_categories_unaffected(self):
        self.assertEqual(classify("too many arguments to function 'foo'"), Category.TYPE_ERROR)
        self.assertEqual(classify("expected ';' before '}' token"), Category.SYNTAX_ERROR)
        self.assertEqual(classify("No module named 'x'"), Category.IMPORT_ERROR)


if __name__ == "__main__":
    unittest.main()
