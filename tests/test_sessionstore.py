"""Chats survive a restart, expire, can be deleted, and a disk problem never breaks the chat."""
import os
import tempfile
import time
import unittest
from pathlib import Path

from rag import privacy, server, sessionstore
from tests.test_server import FakeBot


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "s.db"
        self.store = sessionstore.SessionStore(self.path, ttl=100)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_round_trip_and_key_is_hashed(self):
        hist = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        self.store.save("wa:4917612345678", "whatsapp", hist, [{"fid": "f1", "question": "q", "sources": []}], now=0)
        got = self.store.load("wa:4917612345678", now=10)
        self.assertEqual(got["history"], hist)
        self.assertEqual(got["channel"], "whatsapp")
        self.assertEqual(got["log"][0]["fid"], "f1")
        self.store.db.execute("PRAGMA wal_checkpoint(FULL)")
        self.assertNotIn(b"4917612345678", self.path.read_bytes())  # no phone number in the database file

    def test_expired_chat_is_gone_and_deleted(self):
        self.store.save("web:a", "web", [{"role": "user", "content": "hi"}], [], now=0)
        self.assertIsNone(self.store.load("web:a", now=101))
        self.assertEqual(self.store.stats()[0], 0)

    def test_purge_removes_only_old_chats(self):
        self.store.save("web:old", "web", [], [], now=0)
        self.store.save("web:new", "web", [], [], now=90)
        self.assertEqual(self.store.purge(now=150), 1)
        self.assertIsNone(self.store.load("web:old", now=150))
        self.assertIsNotNone(self.store.load("web:new", now=150))

    def test_delete(self):
        self.store.save("web:a", "web", [], [], now=0)
        self.assertTrue(self.store.delete("web:a"))
        self.assertFalse(self.store.delete("web:a"))

    def test_row_cap_drops_the_oldest(self):
        orig = sessionstore.MAX_ROWS
        sessionstore.MAX_ROWS = 3
        try:
            for i in range(5):
                self.store.save(f"web:{i}", "web", [], [], now=i)
        finally:
            sessionstore.MAX_ROWS = orig
        self.assertEqual(self.store.stats()[0], 3)
        self.assertIsNone(self.store.load("web:0", now=5))
        self.assertIsNotNone(self.store.load("web:4", now=5))

    def test_oversized_chat_is_trimmed_not_lost(self):
        big = [{"role": "user", "content": "x" * 50_000}] * 10
        self.store.save("web:big", "web", big, [], now=0)
        got = self.store.load("web:big", now=1)
        self.assertIsNotNone(got)
        self.assertLessEqual(len(got["history"]), 6)

    def test_damaged_rows_are_ignored(self):
        self.store.save("web:a", "web", [{"role": "system", "content": "evil"}, {"role": "user", "content": 5},
                                           {"role": "user", "content": "ok"}], [{"nofid": 1}], now=0)
        got = self.store.load("web:a", now=1)
        self.assertEqual(got["history"], [{"role": "user", "content": "ok"}])
        self.assertEqual(got["log"], [])

    def test_erase_by_text_and_by_whatsapp_number(self):
        self.store.save("web:a", "web", [{"role": "user", "content": "I am Anna, anna@example.com"}], [], now=0)
        self.store.save("web:b", "web", [{"role": "user", "content": "hello"}], [], now=0)
        self.store.save("wa:4917612345678", "whatsapp", [{"role": "user", "content": "hi"}], [], now=0)
        self.assertEqual(self.store.erase_mentions(["ANNA@example.com"]), 1)
        self.assertEqual(self.store.erase_mentions([], whatsapp_digits="4917612345678"), 1)
        self.assertIsNotNone(self.store.load("web:b", now=1))

    def test_disk_error_does_not_raise(self):
        self.store.close()
        self.store.save("web:a", "web", [], [], now=0)  # closed database: reported on stderr, not raised
        self.assertIsNone(self.store.load("web:a", now=0))


class SessionsRestartTests(unittest.TestCase):
    def setUp(self):
        self.orig = server.Assistant
        server.Assistant = FakeBot
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "s.db"

    def tearDown(self):
        server.Assistant = self.orig
        self.tmp.cleanup()

    def new_server(self):
        return server.Sessions(index=None, store=sessionstore.SessionStore(self.path))

    def test_chat_continues_after_restart(self):
        s1 = self.new_server()
        bot, _, new = s1.get("web:abc", "web", now=0)
        self.assertTrue(new)
        bot.history = [{"role": "user", "content": "hair?"}, {"role": "assistant", "content": "yes"}]
        s1.remember("web:abc", "fid1", "hair?", ["a.md"])
        s1.save("web:abc", "web", now=1)
        s1.store.close()
        s2 = self.new_server()  # "restart": a new Sessions object with an empty memory
        bot2, _, new2 = s2.get("web:abc", "web", now=5)
        self.assertFalse(new2)  # not a new chat, so WhatsApp does not repeat the disclosure
        self.assertEqual(bot2.history[-1]["content"], "yes")
        self.assertEqual(s2.find("web:abc", "fid1")["question"], "hair?")
        s2.store.close()

    def test_rating_works_right_after_restart_before_the_next_message(self):
        s1 = self.new_server()
        s1.get("web:abc", "web", now=0)
        s1.remember("web:abc", "fid1", "hair?", [])
        s1.save("web:abc", "web", now=time.time())  # find() uses the real clock
        s1.store.close()
        s2 = self.new_server()
        try:
            self.assertEqual(s2.find("web:abc", "fid1")["fid"], "fid1")
        finally:
            s2.store.close()

    def test_expired_chat_starts_fresh(self):
        s1 = self.new_server()
        bot, _, _ = s1.get("web:abc", "web", now=0)
        bot.history = [{"role": "user", "content": "old"}]
        s1.save("web:abc", "web", now=0)
        s1.store.close()
        s2 = self.new_server()
        _, _, new = s2.get("web:abc", "web", now=server.SESSION_TTL + 5)
        self.assertTrue(new)
        s2.store.close()

    def test_forget_removes_the_stored_copy(self):
        s1 = self.new_server()
        s1.get("web:abc", "web", now=0)
        s1.save("web:abc", "web", now=0)
        self.assertTrue(s1.forget("web:abc"))
        s1.store.close()
        s2 = self.new_server()
        _, _, new = s2.get("web:abc", "web", now=1)
        self.assertTrue(new)
        s2.store.close()

    def test_other_channel_does_not_pick_up_the_chat(self):
        s1 = self.new_server()
        s1.get("k", "web", now=0)
        s1.save("k", "web", now=0)
        s1.store.close()
        s2 = self.new_server()
        _, _, new = s2.get("k", "whatsapp", now=1)
        self.assertTrue(new)
        s2.store.close()

    def test_without_a_store_nothing_changes(self):
        s = server.Sessions(index=None)
        s.get("x", "web", now=0)
        s.save("x", "web")  # no-op
        self.assertTrue(s.forget("x"))


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SESSIONS_DIR"] = self.tmp.name
        os.environ["PERSIST_SESSIONS"] = "on"
        self.store = sessionstore.SessionStore(sessionstore.default_path())

    def tearDown(self):
        self.store.close()
        os.environ.pop("SESSIONS_DIR", None)
        os.environ["PERSIST_SESSIONS"] = "off"
        self.tmp.cleanup()

    def test_erase_contact_removes_open_chats(self):
        self.store.save("web:a", "web", [{"role": "user", "content": "mail me: Anna@Example.com"}], [], now=0)
        self.store.save("wa:4917612345678", "whatsapp", [{"role": "user", "content": "hi"}], [], now=0)
        self.assertEqual(privacy.erase_sessions("anna@example.com"), 1)
        self.assertEqual(privacy.erase_sessions("+49 176 12345678"), 1)
        self.assertEqual(self.store.stats()[0], 0)

    def test_purge_reports_sessions(self):
        self.store.save("web:a", "web", [], [], now=0)  # saved at time 0: long expired
        self.assertEqual(privacy.purge()["sessions"], 1)


if __name__ == "__main__":
    unittest.main()
