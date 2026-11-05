"""Privacy tool tests (retention, erasure). They touch only temporary folders."""
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rag import feedback, handoff, privacy

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
ENV_KEYS = ("HANDOFF_DIR", "FEEDBACK_DIR", "GAPS_DIR", "RETENTION_HANDOFF_DAYS", "RETENTION_FEEDBACK_DAYS",
            "RETENTION_LOGS_DAYS", "RETENTION_GAPS_DAYS", "PRIVACY_URL")


def ago(days):
    return (NOW - timedelta(days=days)).isoformat()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        os.environ["HANDOFF_DIR"] = str(self.root / "handoffs")
        os.environ["FEEDBACK_DIR"] = str(self.root / "feedback")
        os.environ["GAPS_DIR"] = str(self.root / "gaps")
        for k in ENV_KEYS[3:]:
            os.environ.pop(k, None)
        self.orig_log = privacy.LOG_PATH
        privacy.LOG_PATH = self.root / "conversations.jsonl"
        self.addCleanup(self.restore)

    def restore(self):
        privacy.LOG_PATH = self.orig_log
        for k in ENV_KEYS:
            os.environ.pop(k, None)

    def write_jsonl(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows), encoding="utf-8")

    def read_jsonl(self, path):
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


class SettingsTests(Base):
    def test_retention_defaults_zero_and_bad_values(self):
        self.assertEqual(privacy.retention_days("RETENTION_HANDOFF_DAYS"), 180)
        for raw, want in (("30", 30), ("0", 0), ("abc", 180), ("-5", 180), ("", 180), ("  7 ", 7)):
            os.environ["RETENTION_HANDOFF_DAYS"] = raw
            self.assertEqual(privacy.retention_days("RETENTION_HANDOFF_DAYS"), want, raw)

    def test_privacy_url_uses_the_same_strict_checks_as_the_booking_link(self):
        self.assertIsNone(privacy.privacy_url())
        os.environ["PRIVACY_URL"] = "https://faiyke.com/datenschutz"
        self.assertEqual(privacy.privacy_url(), "https://faiyke.com/datenschutz")
        for bad in ("javascript:alert(1)", "http://faiyke.com/p", "https://user:pw@faiyke.com/p", "https://127.0.0.1/p"):
            os.environ["PRIVACY_URL"] = bad
            self.assertIsNone(privacy.privacy_url(), bad)


class RewriteTests(Base):
    def test_removes_matching_rows_keeps_unreadable_lines_and_leaves_no_temp_file(self):
        p = self.root / "a.jsonl"
        self.write_jsonl(p, [{"n": 1}, "this is not json", {"n": 2}, {"n": 3}])
        removed = privacy.rewrite_jsonl(p, lambda r: r["n"] != 2, threading.Lock())
        self.assertEqual(removed, 1)
        self.assertEqual(p.read_text(encoding="utf-8").splitlines(), ['{"n": 1}', "this is not json", '{"n": 3}'])
        self.assertEqual([f.name for f in self.root.iterdir() if f.name.endswith(".tmp")], [])

    def test_nothing_removed_leaves_the_file_alone_and_missing_file_is_fine(self):
        p = self.root / "a.jsonl"
        self.write_jsonl(p, [{"n": 1}])
        before = p.read_bytes()
        self.assertEqual(privacy.rewrite_jsonl(p, lambda r: True, threading.Lock()), 0)
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual(privacy.rewrite_jsonl(self.root / "missing.jsonl", lambda r: False, threading.Lock()), 0)


class PurgeTests(Base):
    def make(self):
        self.write_jsonl(self.root / "handoffs" / "handoffs.jsonl", [
            {"reference": "FAI-OLD", "time": ago(400), "contact": "a@x.de"},
            {"reference": "FAI-NEW", "time": ago(10), "contact": "b@x.de"},
            {"reference": "FAI-NOTIME", "contact": "c@x.de"},
        ])
        (self.root / "handoffs" / "emailed.txt").write_text("FAI-OLD\nFAI-NEW\n", encoding="utf-8")
        self.write_jsonl(self.root / "feedback" / "feedback.jsonl", [
            {"rating": "up", "time": ago(200)}, {"rating": "down", "time": ago(5)}])
        self.write_jsonl(privacy.LOG_PATH, [{"question": "old", "time": ago(90)}, {"question": "new", "time": ago(1)}])
        self.write_jsonl(self.root / "gaps" / "gaps.jsonl", [
            {"kind": "no_match", "question": "old gap question", "time": ago(100)},
            {"kind": "no_match", "question": "new gap question", "time": ago(3)}])

    def test_old_records_are_deleted_and_new_or_undated_ones_kept(self):
        self.make()
        out = privacy.purge(NOW)
        self.assertEqual(out, {"handoffs": 1, "feedback": 1, "logs": 1, "gaps": 1, "sessions": 0})
        self.assertEqual([r["question"] for r in self.read_jsonl(self.root / "gaps" / "gaps.jsonl")], ["new gap question"])
        self.assertEqual([r["reference"] for r in self.read_jsonl(self.root / "handoffs" / "handoffs.jsonl")], ["FAI-NEW", "FAI-NOTIME"])
        self.assertEqual([r["rating"] for r in self.read_jsonl(self.root / "feedback" / "feedback.jsonl")], ["down"])
        self.assertEqual([r["question"] for r in self.read_jsonl(privacy.LOG_PATH)], ["new"])
        self.assertEqual((self.root / "handoffs" / "emailed.txt").read_text().split(), ["FAI-NEW"])

    def test_zero_switches_a_deletion_off(self):
        self.make()
        os.environ["RETENTION_HANDOFF_DAYS"] = "0"
        out = privacy.purge(NOW)
        self.assertEqual(out["handoffs"], 0)
        self.assertEqual(len(self.read_jsonl(self.root / "handoffs" / "handoffs.jsonl")), 3)

    def test_purge_with_no_files_is_fine(self):
        self.assertEqual(privacy.purge(NOW), {"handoffs": 0, "feedback": 0, "logs": 0, "gaps": 0, "sessions": 0})

    def test_background_job_runs_a_purge_and_never_dies_on_errors(self):
        calls = []

        def fake_purge(now=None):
            calls.append(1)
            raise RuntimeError("boom")
        orig = privacy.purge
        privacy.purge = fake_purge
        try:
            t = privacy.start_background()
            deadline = time.time() + 3
            while not calls and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual(len(calls), 1)
            self.assertTrue(t.daemon and t.is_alive())
        finally:
            privacy.purge = orig


class EraseTests(Base):
    def setUp(self):
        super().setUp()
        self.path = self.root / "handoffs" / "handoffs.jsonl"
        self.write_jsonl(self.path, [
            {"reference": "FAI-1", "contact": "Anna@Example.com", "name": "Anna"},
            {"reference": "FAI-2", "contact": "+49 176 41565516", "name": "Ben"},
            {"reference": "FAI-3", "contact": "someone@else.org", "name": "Cleo"},
            {"reference": "FAI-4", "contact": "anna@example.com", "name": "Anna again"},
        ])
        (self.root / "handoffs" / "emailed.txt").write_text("FAI-1\nFAI-2\nFAI-3\n", encoding="utf-8")

    def refs(self):
        return [r["reference"] for r in self.read_jsonl(self.path)]

    def test_by_email_ignores_case_and_removes_all_of_that_persons_records(self):
        self.assertEqual(privacy.erase_handoffs(contact="anna@example.COM"), ["FAI-1", "FAI-4"])
        self.assertEqual(self.refs(), ["FAI-2", "FAI-3"])
        self.assertEqual((self.root / "handoffs" / "emailed.txt").read_text().split(), ["FAI-2", "FAI-3"])

    def test_by_phone_ignores_spacing_and_00_prefix(self):
        self.assertEqual(privacy.erase_handoffs(contact="0049 176-4156 5516"), ["FAI-2"])

    def test_by_reference_removes_only_that_one(self):
        self.assertEqual(privacy.erase_handoffs(reference="FAI-3"), ["FAI-3"])
        self.assertEqual(self.refs(), ["FAI-1", "FAI-2", "FAI-4"])

    def test_no_match_removes_nothing_and_needs_a_criterion(self):
        self.assertEqual(privacy.erase_handoffs(contact="nobody@nowhere.com"), [])
        self.assertEqual(len(self.refs()), 4)
        with self.assertRaises(ValueError):
            privacy.erase_handoffs()

    def test_an_empty_contact_never_matches_records_with_empty_contacts(self):
        self.write_jsonl(self.path, [{"reference": "FAI-9", "contact": "-"}])
        self.assertEqual(privacy.erase_handoffs(contact="-"), [])

    def test_normalise_contact(self):
        n = privacy.normalise_contact
        self.assertEqual(n("  Me@X.de "), "me@x.de")
        self.assertEqual(n("+49 (176) 415-65516"), "4917641565516")
        self.assertEqual(n("0049176 41565516"), "4917641565516")
        self.assertEqual(n(""), "")


class FeedbackForgetTests(Base):
    def test_forget_removes_only_that_sessions_ratings(self):
        store = feedback.FeedbackStore(self.root / "feedback")
        fid = "0123456789abcdef"
        store.record("up", fid, "", "session-aaaa-1111")
        store.record("down", fid, "bad", "session-aaaa-1111")
        store.record("up", fid, "", "session-bbbb-2222")
        self.assertEqual(store.forget("session-aaaa-1111"), 2)
        rows = self.read_jsonl(store.path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session"], feedback.session_hash("session-bbbb-2222"))
        self.assertEqual(store.forget("session-aaaa-1111"), 0)

    def test_no_ratings_are_lost_when_purge_and_saving_happen_together(self):
        store = feedback.FeedbackStore(self.root / "feedback", daily_cap=10_000)
        stop = threading.Event()

        def purger():
            while not stop.is_set():
                store.rewrite(lambda r: True)  # rewrites the file but removes nothing
        t = threading.Thread(target=purger)
        t.start()
        try:
            for i in range(150):
                store.record("up", "0123456789abcdef", "", f"session-{i:04d}-xxxx")
        finally:
            stop.set()
            t.join()
        self.assertEqual(len(self.read_jsonl(store.path)), 150)


if __name__ == "__main__":
    unittest.main()
