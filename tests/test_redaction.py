import unittest
from helpers import *  # noqa
from aiterm.security.redact import redact, find_secrets, is_sensitive_path


class Redaction(unittest.TestCase):
    def test_assignments(self):
        out = redact('API_KEY=abc123secret\nPASSWORD = "hunter2"\nTOKEN: xyz789\nname = "bob"')
        self.assertNotIn("abc123secret", out)
        self.assertNotIn("hunter2", out)
        self.assertNotIn("xyz789", out)
        self.assertIn('name = "bob"', out)
        self.assertIn("API_KEY=********", out)

    def test_known_formats(self):
        for s in ["AKIAABCDEFGHIJKLMNOP", "ghp_" + "a" * 30, "sk-" + "b" * 30, "AIza" + "c" * 35,
                  "eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4fw"]:
            self.assertNotIn(s, redact(f"x {s} y"), s)

    def test_private_key_block(self):
        pk = "-----BEGIN RSA PRIVATE KEY-----\nMIIEabc\ndef\n-----END RSA PRIVATE KEY-----"
        out = redact("before\n" + pk + "\nafter")
        self.assertNotIn("MIIEabc", out)
        self.assertIn("after", out)

    def test_url_credentials_and_bearer(self):
        out = redact("postgres://user:s3cretpw@host/db  Authorization: Bearer abcdefghijklmnopqrstuvwx")
        self.assertNotIn("s3cretpw", out)
        self.assertNotIn("abcdefghijklmnopqrstuvwx", out)

    def test_code_is_not_mangled(self):
        code = "def f(password):\n    token = os.environ['X']\n    return password"
        self.assertEqual(redact(code), code)

    def test_sensitive_paths(self):
        for p in [".env", ".env.local", "id_rsa", "server.pem", "credentials.json", "prod.tfvars"]:
            self.assertTrue(is_sensitive_path(p), p)
        self.assertFalse(is_sensitive_path("main.py"))

    def test_find_secrets(self):
        self.assertTrue(find_secrets("password=abcdef"))
        self.assertFalse(find_secrets("print('hi')"))


if __name__ == "__main__":
    unittest.main()
