import json
import unittest
from unittest import mock
from helpers import *  # noqa
from aiterm.ai.base import AIProvider, AIUnavailable, parse_ai_json
from aiterm.ai.context import build_context
from aiterm.ai.engine import AIEngine
from aiterm.ai.providers import MockProvider, build_provider, GeminiProvider, OpenAIProvider, LocalModelProvider
from aiterm.core.config import AIConfig
from aiterm.core.models import Diagnostic


def diag(file="a.py", line=3, msg="boom"):
    return Diagnostic(file, line, 0, "error", "RUNTIME_ERROR", msg, "python-runtime")


class Context(unittest.TestCase):
    def test_only_relevant_lines_and_redacted(self):
        root = tmpdir()
        body = "\n".join(f"filler_{i} = {i}" for i in range(100))
        write(root, "a.py", "import os\n" + body + "\nAPI_KEY = 'sk-" + "z" * 30 + "'\nprint(1)\n")
        d = diag(line=102, msg="bad token sk-" + "q" * 30)
        ctx = build_context(d, root, AIConfig(context_lines=3))
        self.assertNotIn("z" * 30, ctx.text)
        self.assertNotIn("q" * 30, ctx.text)
        self.assertNotIn("filler_5 ", ctx.text)          # far-away lines are NOT sent
        self.assertIn("DETECTED FACT", ctx.text)
        self.assertTrue(ctx.redacted)

    def test_env_file_never_sent(self):
        root = tmpdir()
        write(root, ".env", "SECRET_TOKEN=supersecretvalue\n")
        ctx = build_context(diag(file=".env", line=1), root, AIConfig())
        self.assertNotIn("supersecretvalue", ctx.text)
        self.assertEqual(ctx.files, [])
        self.assertIn("withheld", ctx.text)

    def test_path_traversal_refused(self):
        root = tmpdir()
        outside = write(tmpdir(), "x.py", "SECRET=1\nprint('outside')\n")
        ctx = build_context(diag(file=str(outside), line=1), root, AIConfig())
        self.assertNotIn("outside", ctx.text)

    def test_enclosing_function_and_imports(self):
        root = tmpdir()
        write(root, "a.py", "import os\n\ndef f(x):\n    return x / 0\n\ndef g():\n    pass\n")
        ctx = build_context(diag(line=4), root, AIConfig())
        self.assertIn("ENCLOSING FUNCTION", ctx.text)
        self.assertIn("import os", ctx.text)
        self.assertNotIn("def g", ctx.text.split("ENCLOSING FUNCTION")[1].split("## IMPORTS")[0])


class Parsing(unittest.TestCase):
    def test_good_json_and_fenced(self):
        j = {"problem": "p", "cause": "c", "explanation": "e", "suggested_fix": "s", "confidence": 0.91,
             "requires_manual_review": False, "fixed_line": "x = 1"}
        for txt in (json.dumps(j), "```json\n" + json.dumps(j) + "\n```", "Sure! " + json.dumps(j)):
            r = parse_ai_json(txt)
            self.assertEqual((r.problem, r.confidence, r.fixed_line), ("p", 0.91, "x = 1"))

    def test_garbage_is_flagged_for_review(self):
        r = parse_ai_json("I think you should try turning it off and on")
        self.assertTrue(r.requires_manual_review)
        self.assertEqual(r.confidence, 0.0)

    def test_confidence_clamped_and_multiline_fix_dropped(self):
        r = parse_ai_json(json.dumps({"confidence": 7, "fixed_line": "a\nb"}))
        self.assertEqual(r.confidence, 1.0)
        self.assertIsNone(r.fixed_line)


class Engine(unittest.TestCase):
    def setUp(self):
        self.root = tmpdir()
        write(self.root, "a.py", "x = 1 / 0\n")

    def test_disabled_makes_no_calls(self):
        p = MockProvider()
        e = AIEngine(AIConfig(enabled=False), p)
        self.assertIsNone(e.explain(diag(line=1), self.root))
        self.assertEqual(p.calls, 0)

    def test_cache_and_dedup(self):
        p = MockProvider()
        e = AIEngine(AIConfig(enabled=True, provider="mock"), p)
        for _ in range(4):
            self.assertIsNotNone(e.explain(diag(line=1), self.root))
        self.assertEqual(p.calls, 1)

    def test_provider_failure_degrades_gracefully(self):
        class Down(AIProvider):
            name = "down"
            def complete(self, s, u): raise AIUnavailable("network unreachable")
        e = AIEngine(AIConfig(enabled=True), Down())
        self.assertIsNone(e.explain(diag(line=1), self.root))
        self.assertIn("network", e.last_error)

    def test_unexpected_provider_exception_contained(self):
        class Bug(AIProvider):
            name = "bug"
            def complete(self, s, u): raise ValueError("secret-key-abc in message")
        e = AIEngine(AIConfig(enabled=True), Bug())
        self.assertIsNone(e.explain(diag(line=1), self.root))
        self.assertNotIn("secret-key-abc", e.last_error)

    def test_prompt_sent_to_provider_is_redacted(self):
        write(self.root, "b.py", "password = 'hunter2hunter2'\nprint(1)\n")
        seen = []
        class Spy(AIProvider):
            name = "spy"
            def complete(self, s, u): seen.append(u); return "{}"
        AIEngine(AIConfig(enabled=True), Spy()).explain(diag(file="b.py", line=2), self.root)
        self.assertTrue(seen)
        self.assertNotIn("hunter2hunter2", seen[0])


class Providers(unittest.TestCase):
    def test_factory(self):
        for n, cls in [("gemini", GeminiProvider), ("openai", OpenAIProvider), ("local", LocalModelProvider), ("mock", MockProvider)]:
            self.assertIsInstance(build_provider(AIConfig(provider=n)), cls)
        with self.assertRaises(AIUnavailable):
            build_provider(AIConfig(provider="nope"))

    def test_missing_key_and_model(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AIUnavailable):
                GeminiProvider(AIConfig(model="m")).complete("s", "u")
            with self.assertRaises(AIUnavailable):
                OpenAIProvider(AIConfig()).complete("s", "u")

    def test_http_error_does_not_leak_key(self):
        import urllib.error
        err = urllib.error.HTTPError("https://x?key=TOPSECRET", 401, "no", {}, None)
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "TOPSECRET"}), \
                mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(AIUnavailable) as cm:
                GeminiProvider(AIConfig(model="m")).complete("s", "u")
        self.assertNotIn("TOPSECRET", str(cm.exception))
        self.assertIn("API key", str(cm.exception))

    def test_timeout_maps_to_unavailable(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
            with self.assertRaises(AIUnavailable):
                LocalModelProvider(AIConfig(model="m")).complete("s", "u")

    def test_openai_response_shape(self):
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): pass
            def read(s): return json.dumps({"choices": [{"message": {"content": "hello"}}]}).encode()
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "k"}), mock.patch("urllib.request.urlopen", return_value=R()):
            self.assertEqual(OpenAIProvider(AIConfig(model="m")).complete("s", "u"), "hello")


if __name__ == "__main__":
    unittest.main()
