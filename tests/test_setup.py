"""Tests for .env loading and the WhatsApp setup helper. No network, no secrets."""
import os
import pathlib
import tempfile
import unittest
import urllib.error

from rag import env, whatsapp_setup


class EnvTests(unittest.TestCase):
    def test_parse(self):
        text = "# comment\nA=1\nB = two words \nC=\"quoted\"\nD='single'\n\nnot a line\nE=x=y\n"
        self.assertEqual(env.parse(text), {"A": "1", "B": "two words", "C": "quoted", "D": "single", "E": "x=y"})

    def test_load_does_not_overwrite_or_set_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / ".env"
            p.write_text("FAIYKE_T1=file\nFAIYKE_T2=file\nFAIYKE_T3=\n", encoding="utf-8")
            os.environ["FAIYKE_T1"] = "real"
            os.environ.pop("FAIYKE_T2", None)
            os.environ.pop("FAIYKE_T3", None)
            try:
                names = env.load(p)
                self.assertEqual(os.environ["FAIYKE_T1"], "real")
                self.assertEqual(os.environ["FAIYKE_T2"], "file")
                self.assertNotIn("FAIYKE_T3", os.environ)
                self.assertEqual(names, ["FAIYKE_T2"])
            finally:
                for k in ("FAIYKE_T1", "FAIYKE_T2", "FAIYKE_T3"):
                    os.environ.pop(k, None)

    def test_load_missing_file(self):
        self.assertEqual(env.load(pathlib.Path("does-not-exist.env")), [])


class SetupTests(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(whatsapp_setup.missing({}), list(whatsapp_setup.REQUIRED))
        full = {k: "x" for k in whatsapp_setup.REQUIRED}
        self.assertEqual(whatsapp_setup.missing(full), [])

    def test_webhook_ok(self):
        ok, _ = whatsapp_setup.check_webhook("https://x.example/", "tok", getter=lambda url: (200, "faiyke-test-12345"))
        self.assertTrue(ok)

    def test_webhook_wrong_token_is_explained(self):
        def getter(url):
            raise urllib.error.HTTPError(url, 403, "forbidden", {}, None)

        ok, msg = whatsapp_setup.check_webhook("https://x.example", "tok", getter=getter)
        self.assertFalse(ok)
        self.assertIn("403", msg)

    def test_webhook_unreachable(self):
        def getter(url):
            raise OSError("connection refused")

        ok, msg = whatsapp_setup.check_webhook("https://x.example", "tok", getter=getter)
        self.assertFalse(ok)
        self.assertIn("running", msg)

    def test_webhook_url_contains_verify_token(self):
        seen = []
        whatsapp_setup.check_webhook("https://x.example", "my secret", getter=lambda url: seen.append(url) or (200, "nope"))
        self.assertIn("hub.verify_token=my+secret", seen[0])
        self.assertTrue(seen[0].startswith("https://x.example/webhook/whatsapp?"))


if __name__ == "__main__":
    unittest.main()
