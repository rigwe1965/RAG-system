"""Feedback tests. No API key, no network."""
import json
import tempfile
import unittest
from pathlib import Path

from rag import feedback


class ValidateTests(unittest.TestCase):
    fid = "0123456789abcdef"

    def test_accepts_good_input(self):
        out = feedback.validate({"rating": "down", "fid": self.fid, "comment": "wrong price"})
        self.assertEqual(out, {"rating": "down", "fid": self.fid, "comment": "wrong price"})

    def test_rejects_bad_input(self):
        bad = [
            None, [], "up", {},
            {"rating": "sideways", "fid": self.fid},
            {"rating": "up", "fid": "../../etc/passwd"},
            {"rating": "up", "fid": self.fid.upper()},
            {"rating": "up", "fid": 123},
            {"rating": "down", "fid": self.fid, "comment": "x" * (feedback.MAX_COMMENT + 1)},
            {"rating": "down", "fid": self.fid, "comment": {"a": 1}},
        ]
        for data in bad:
            with self.assertRaises(feedback.FeedbackError, msg=repr(data)):
                feedback.validate(data)

    def test_thumbs_up_drops_comment(self):
        self.assertEqual(feedback.validate({"rating": "up", "fid": self.fid, "comment": "hi"})["comment"], "")


class ScrubTests(unittest.TestCase):
    def test_removes_contact_details_and_control_characters(self):
        out = feedback.scrub("mail me at anna@example.com or +49 176 41565516\x00\nthanks", 300)
        self.assertNotIn("anna@example.com", out)
        self.assertNotIn("41565516", out)
        self.assertNotIn("\x00", out)
        self.assertNotIn("\n", out)

    def test_cuts_to_limit(self):
        self.assertEqual(len(feedback.scrub("a" * 1000, 50)), 50)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = feedback.FeedbackStore(self.tmp.name, daily_cap=2)

    def rows(self):
        p = Path(self.tmp.name) / "feedback.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def test_raw_session_id_is_never_stored(self):
        sid = "abcdef1234567890"
        self.store.record("down", "0123456789abcdef", "", sid, {"question": "q", "sources": ["a.md"]})
        text = (Path(self.tmp.name) / "feedback.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(sid, text)

    def test_question_saved_only_for_thumbs_down_and_scrubbed(self):
        ctx = {"question": "my email is bob@example.com, what is the price?", "sources": ["x.md"]}
        self.store.record("down", "0123456789abcdef", "", "abcdef1234567890", ctx)
        self.store.record("up", "0123456789abcdef", "", "abcdef1234567890", ctx)
        down, up = self.rows()
        self.assertIn("what is the price", down["question"])
        self.assertNotIn("bob@example.com", down["question"])
        self.assertIsNone(up["question"])
        self.assertEqual(up["sources"], ["x.md"])

    def test_log_injection_stays_one_line_per_entry(self):
        comment = feedback.validate({"rating": "down", "fid": "0123456789abcdef", "comment": 'a"}\n{"rating":"up'})["comment"]
        self.store.record("down", "0123456789abcdef", comment, "abcdef1234567890")
        self.assertEqual(len(self.rows()), 1)

    def test_daily_cap(self):
        self.assertTrue(self.store.record("up", "0123456789abcdef", "", "", today="2026-11-05"))
        self.assertTrue(self.store.record("up", "0123456789abcdef", "", "", today="2026-11-05"))
        self.assertFalse(self.store.record("up", "0123456789abcdef", "", "", today="2026-11-05"))
        self.assertTrue(self.store.record("up", "0123456789abcdef", "", "", today="2026-11-06"))

    def test_file_size_cap(self):
        self.store.folder.mkdir(parents=True, exist_ok=True)
        self.store.path.write_bytes(b"x" * feedback.MAX_FILE_BYTES)
        self.assertFalse(self.store.record("up", "0123456789abcdef", "", ""))


if __name__ == "__main__":
    unittest.main()
