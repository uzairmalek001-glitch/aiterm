"""Generates examples/stress_project: 1000+ lines of realistic code, each file hiding ONE intentional mistake.
Also writes MANIFEST.json (file -> expected category / detection mode) used by tests/test_stress.py."""
import json
import textwrap
from pathlib import Path

OUT = Path(__file__).parent / "stress_project"

def filler(seed: int) -> str:
    return textwrap.dedent(f'''\
    def helper_{seed}_sum(values):
        """Sum numbers, skipping None."""
        total = 0
        for v in values:
            if v is not None:
                total += v
        return total


    def helper_{seed}_stats(values):
        clean = [v for v in values if v is not None]
        if not clean:
            return {{"min": None, "max": None, "mean": None}}
        return {{"min": min(clean), "max": max(clean), "mean": sum(clean) / len(clean)}}


    class Box{seed}:
        def __init__(self, items=None):
            self.items = list(items or [])

        def add(self, item):
            self.items.append(item)
            return self

        def total(self):
            return helper_{seed}_sum(self.items)

    ''')

# (name, buggy snippet, expected category, mode)   mode: static = found without running, runtime = found via `aiterm run`
PY_SYNTAX = [
    ("missing_colon_for", "def f(items):\n    for i in items\n        print(i)\n", "SYNTAX_ERROR"),
    ("missing_colon_if", "def f(x):\n    if x > 1\n        return x\n", "SYNTAX_ERROR"),
    ("missing_colon_def", "def f(x)\n    return x\n", "SYNTAX_ERROR"),
    ("missing_colon_class", "class Foo\n    pass\n", "SYNTAX_ERROR"),
    ("missing_colon_while", "def f():\n    while True\n        break\n", "SYNTAX_ERROR"),
    ("unclosed_paren", "def f():\n    print((1 + 2)\n    return 3\n", "SYNTAX_ERROR"),
    ("unclosed_bracket", "data = [1, 2, 3\nprint(data)\n", "SYNTAX_ERROR"),
    ("unclosed_brace", "cfg = {'a': 1, 'b': 2\nprint(cfg)\n", "SYNTAX_ERROR"),
    ("unterminated_string", "msg = 'hello\nprint(msg)\n", "SYNTAX_ERROR"),
    ("unterminated_triple", 'doc = """never closed\nprint(doc)\n', "SYNTAX_ERROR"),
    ("bad_indent", "def f():\nreturn 1\n", "SYNTAX_ERROR"),
    ("unexpected_indent", "x = 1\n    y = 2\n", "SYNTAX_ERROR"),
    ("unindent_mismatch", "def f():\n        a = 1\n    b = 2\n", "SYNTAX_ERROR"),
    ("py2_print", "def f():\n    print 'hello'\n", "SYNTAX_ERROR"),
    ("double_equals_assign", "x = = 1\n", "SYNTAX_ERROR"),
    ("assign_to_literal", "1 = x\n", "SYNTAX_ERROR"),
    ("else_without_if", "def f(x):\n    else:\n        return 1\n", "SYNTAX_ERROR"),
    ("bad_def_args", "def f(:\n    pass\n", "SYNTAX_ERROR"),
    ("missing_comma_dict", "d = {'a': 1 'b': 2}\n", "SYNTAX_ERROR"),
    ("keyword_as_name", "class = 5\n", "SYNTAX_ERROR"),
    ("incomplete_import", "import\n", "SYNTAX_ERROR"),
    ("bad_fstring", "name = 'x'\nprint(f'{name')\n", "SYNTAX_ERROR"),
    ("mismatched_brackets", "x = (1, 2]\n", "SYNTAX_ERROR"),
    ("dangling_operator", "total = 1 +\n", "SYNTAX_ERROR"),
    ("lambda_bad", "f = lambda x: \n", "SYNTAX_ERROR"),
    ("decorator_alone", "@decorator\n", "SYNTAX_ERROR"),
    ("try_without_except", "def f():\n    try:\n        return 1\n    print('x')\n", "SYNTAX_ERROR"),
]
PY_IMPORT = [
    ("missing_third_party", "import totally_missing_package_abc\n", "IMPORT_ERROR"),
    ("missing_from_import", "from nonexistent_lib_xyz import thing\n", "IMPORT_ERROR"),
    ("missing_submodule", "import another_missing_pkg.sub.module\n", "IMPORT_ERROR"),
]
PY_RUNTIME = [
    ("zero_division", "def avg(xs):\n    return sum(xs) / len(xs)\n\nprint(avg([]))\n", "ZeroDivisionError"),
    ("key_error", "cfg = {'a': 1}\nprint(cfg['missing'])\n", "KeyError"),
    ("type_error", "print('total: ' + 5)\n", "TypeError"),
    ("index_error", "items = [1, 2, 3]\nprint(items[10])\n", "IndexError"),
    ("attribute_error", "x = 5\nprint(x.append(1))\n", "AttributeError"),
    ("name_error", "def f():\n    return undefined_variable + 1\n\nprint(f())\n", "NameError"),
    ("value_error", "print(int('not a number'))\n", "ValueError"),
    ("file_not_found", "open('/nonexistent/path/file.txt').read()\n", "FileNotFoundError"),
    ("assertion", "def check(n):\n    assert n > 0, 'n must be positive'\n\ncheck(-1)\n", "AssertionError"),
    ("recursion", "def f(n):\n    return f(n + 1)\n\nf(0)\n", "RecursionError"),
    ("unbound_local", "def f():\n    print(total)\n    total = 1\n\nf()\n", "UnboundLocalError"),
    ("stop_iteration", "it = iter([])\nprint(next(it))\n", "StopIteration"),
]

C_CASES = [
    ("missing_semicolon.c", "#include <stdio.h>\nint main(void) {\n    int x = 5\n    printf(\"%d\\n\", x);\n    return 0;\n}\n", "SYNTAX_ERROR"),
    ("undeclared_var.c", "#include <stdio.h>\nint main(void) {\n    printf(\"%d\\n\", y);\n    return 0;\n}\n", "COMPILATION_ERROR"),
    ("too_many_args.c", "int add(int a, int b) { return a + b; }\nint main(void) { return add(1, 2, 3); }\n", "TYPE_ERROR"),
    ("unterminated_string.c", "#include <stdio.h>\nint main(void) {\n    printf(\"hello);\n    return 0;\n}\n", "SYNTAX_ERROR"),
    ("missing_brace.c", "int main(void) {\n    if (1) {\n        return 0;\n    return 1;\n}\n", "SYNTAX_ERROR"),
    ("missing_header.c", "#include <not_a_real_header.h>\nint main(void) { return 0; }\n", "IMPORT_ERROR"),
    ("wrong_type.c", "int main(void) {\n    int *p = 5.5;\n    return 0;\n}\n", "TYPE_ERROR"),
    ("undefined_func.cpp", "int main() {\n    missing_function(3);\n    return 0;\n}\n", "COMPILATION_ERROR"),
    ("cpp_no_match.cpp", "int foo(int a, int b) { return a + b; }\nint main() { return foo(1, 2, 3); }\n", "TYPE_ERROR"),
    ("cpp_missing_semi.cpp", "#include <iostream>\nint main() {\n    std::cout << \"hi\"\n    return 0;\n}\n", "SYNTAX_ERROR"),
]
JS_CASES = [
    ("unclosed_brace.js", "function f() {\n  return 1;\n", "SYNTAX_ERROR"),
    ("bad_token.js", "const x = ;\n", "SYNTAX_ERROR"),
    ("missing_paren.js", "console.log('a';\n", "SYNTAX_ERROR"),
    ("reserved_word.js", "const class = 1;\n", "SYNTAX_ERROR"),
    ("unterminated_str.js", "const s = 'abc;\n", "SYNTAX_ERROR"),
    ("dup_declare.js", "let a = 1;\nlet a = 2;\n", "SYNTAX_ERROR"),
]
TS_CASES = [
    ("string_to_number.ts", "let n: number = 'hello';\n", "TYPE_ERROR"),
    ("missing_prop.ts", "interface U { id: number; name: string }\nconst u: U = { id: 1 };\n", "TYPE_ERROR"),
    ("wrong_arg.ts", "function f(a: number): number { return a; }\nf('x');\n", "TYPE_ERROR"),
    ("undefined_name.ts", "console.log(nothingHere);\n", "TYPE_ERROR"),
    ("return_type.ts", "function f(): string { return 42; }\n", "TYPE_ERROR"),
    ("missing_semi_brace.ts", "const x = {a: 1,, b: 2};\n", "SYNTAX_ERROR"),
]

def big_module() -> str:
    parts = ["\"\"\"A large, mostly-correct module: the single bug is buried deep to test line reporting.\"\"\"\n"]
    for i in range(24):
        parts.append(filler(1000 + i))
    lines = "".join(parts).splitlines(True)
    # bury one syntax error deep in the file
    idx = next(k for k in range(len(lines) * 3 // 4, len(lines)) if lines[k].lstrip().startswith("for v in values:"))
    lines[idx] = lines[idx].rstrip("\n").rstrip(":") + "\n"
    return "".join(lines), idx + 1

def main():
    OUT.mkdir(exist_ok=True)
    manifest = {}
    n = 0
    for name, snippet, cat in PY_SYNTAX + PY_IMPORT:
        f = OUT / "syntax" / f"{name}.py" if cat == "SYNTAX_ERROR" else OUT / "imports" / f"{name}.py"
        f.parent.mkdir(exist_ok=True)
        n += 1
        f.write_text(f'"""Case {n}: {name}"""\n\n' + filler(n) + "\n\n" + snippet)
        manifest[str(f.relative_to(OUT))] = {"expect": cat, "mode": "static"}
    for name, snippet, exc in PY_RUNTIME:
        f = OUT / "runtime" / f"{name}.py"
        f.parent.mkdir(exist_ok=True)
        n += 1
        f.write_text(f'"""Case {n}: {name} (valid syntax; crashes when run)"""\n\n' + filler(n) + "\n\n" + snippet)
        manifest[str(f.relative_to(OUT))] = {"expect": exc, "mode": "runtime"}
    src, line = big_module()
    (OUT / "big_module.py").write_text(src)
    manifest["big_module.py"] = {"expect": "SYNTAX_ERROR", "mode": "static", "line": line}
    for group, cases in (("c", C_CASES), ("js", JS_CASES), ("ts", TS_CASES)):
        d = OUT / group
        d.mkdir(exist_ok=True)
        for name, code, cat in cases:
            (d / name).write_text(code)
            manifest[f"{group}/{name}"] = {"expect": cat, "mode": "static"}
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    total = sum(len(p.read_text().splitlines()) for p in OUT.rglob("*") if p.suffix in (".py", ".c", ".cpp", ".js", ".ts"))
    print(f"{len(manifest)} files, {total} lines of code")

if __name__ == "__main__":
    main()
