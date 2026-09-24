"""Analyzers backed by external compilers/checkers. Missing tool => analyzer quietly inactive."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from aiterm.analyzers.base import LanguageAnalyzer, register, run_tool
from aiterm.analyzers.parsers import parse_gcc_style, parse_node_check, parse_tsc
from aiterm.core.models import Diagnostic


class ToolAnalyzer(LanguageAnalyzer):
    tool = ""
    timeout = 30.0

    def command(self, path: Path, root: Path, tmp: str) -> Optional[List[str]]:
        raise NotImplementedError

    def parse(self, output: str, path: Path, root: Path) -> List[Diagnostic]:
        return parse_gcc_style(output, self.name, root)

    def available(self) -> bool:
        return shutil.which(self.tool) is not None

    def analyze(self, path: Path, root: Path) -> List[Diagnostic]:
        if not self.available():
            return []
        with tempfile.TemporaryDirectory(prefix="aiterm-") as tmp:
            cmd = self.command(path, root, tmp)
            if not cmd:
                return []
            res = run_tool(cmd, root, self.timeout)
        return self.parse(res[1], path, root) if res else []


@register
class CAnalyzer(ToolAnalyzer):
    name, extensions, tool = "c", (".c",), "gcc"

    def command(self, path, root, tmp):
        return ["gcc", "-fsyntax-only", "-Wall", "-Wextra", "-fdiagnostics-color=never", str(path)]


@register
class CppAnalyzer(ToolAnalyzer):
    name, extensions, tool = "cpp", (".cpp", ".cc", ".cxx", ".hpp", ".hh"), "g++"

    def command(self, path, root, tmp):
        return ["g++", "-std=c++17", "-fsyntax-only", "-Wall", "-Wextra", "-fdiagnostics-color=never", str(path)]


@register
class JavaAnalyzer(ToolAnalyzer):
    name, extensions, tool = "java", (".java",), "javac"

    def command(self, path, root, tmp):
        return ["javac", "-Xlint:all", "-proc:none", "-d", tmp, str(path)]


@register
class KotlinAnalyzer(ToolAnalyzer):
    name, extensions, tool, timeout = "kotlin", (".kt", ".kts"), "kotlinc", 90.0

    def command(self, path, root, tmp):
        return ["kotlinc", str(path), "-d", tmp]


@register
class RustAnalyzer(ToolAnalyzer):
    name, extensions, tool, timeout = "rust", (".rs",), "rustc", 90.0

    def available(self) -> bool:
        return shutil.which("cargo") is not None or shutil.which("rustc") is not None

    def command(self, path, root, tmp):
        if (root / "Cargo.toml").exists() and shutil.which("cargo"):
            return ["cargo", "check", "--message-format=short", "--quiet"]
        if shutil.which("rustc"):
            return ["rustc", "--emit=metadata", "--error-format=short", "--out-dir", tmp, str(path)]
        return None


@register
class TypeScriptAnalyzer(ToolAnalyzer):
    name, extensions, tool, timeout = "typescript", (".ts", ".tsx"), "tsc", 60.0

    def command(self, path, root, tmp):
        if (root / "tsconfig.json").exists():
            return ["tsc", "--noEmit", "--pretty", "false", "-p", str(root)]
        return ["tsc", "--noEmit", "--pretty", "false", str(path)]

    def parse(self, output, path, root):
        return parse_tsc(output, root)


@register
class JavaScriptAnalyzer(ToolAnalyzer):
    name, extensions, tool = "javascript", (".js", ".mjs", ".cjs", ".jsx"), "node"

    def command(self, path, root, tmp):
        return ["node", "--check", str(path)] if path.suffix != ".jsx" else None

    def parse(self, output, path, root):
        return parse_node_check(output, path, root)
