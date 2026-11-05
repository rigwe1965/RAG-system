"""Dashboard upgrade: activity numbers, charts, knowledge-base health and the re-index button."""
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from rag import admin, metrics, server
from tests.test_admin import PASSWORD, Base


class MetricsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = metrics.MetricsStore(Path(self.tmp) / "m.db")
        self.now = time.time()

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_counts_per_day_and_zero_filled(self):
        self.store.record("web", 1.2, sources=["a.md"], now=self.now)
        self.store.record("whatsapp", 2.0, gap="no_match", sources=["a.md", "b.md"], now=self.now)
        self.store.record("web", 0.5, error=True, now=self.now - 86400 * 2)
        r = self.store.report(7, self.now)
        self.assertEqual(len(r["days"]), 7)
        self.assertEqual(r["messages"], 3)
        self.assertEqual(r["errors"], 1)
        today = r["days"][-1]
        self.assertEqual((today["messages"], today["web"], today["whatsapp"], today["gaps"]), (2, 1, 1, 1))
        self.assertEqual(r["days"][-2]["messages"], 0)  # a quiet day is a zero, not a missing bar
        self.assertEqual(dict(r["files"]), {"a.md": 2, "b.md": 1})

    def test_range_excludes_older_days(self):
        self.store.record("web", 1, now=self.now - 86400 * 10)
        self.assertEqual(self.store.report(7, self.now)["messages"], 0)
        self.assertEqual(self.store.report(30, self.now)["messages"], 1)

    def test_answer_time_percentiles(self):
        for sec in [1.0] * 9 + [10.0]:
            self.store.record("web", sec, now=self.now)
        r = self.store.report(7, self.now)
        self.assertLessEqual(r["median_seconds"], 1.5)
        self.assertGreaterEqual(r["p90_seconds"], 1.0)
        self.assertAlmostEqual(r["mean_seconds"], 1.9, places=1)

    def test_no_data_gives_no_times(self):
        r = self.store.report(7, self.now)
        self.assertEqual((r["messages"], r["median_seconds"], r["p90_seconds"]), (0, None, None))

    def test_unknown_channel_and_gap_do_not_break_counting(self):
        self.store.record("telegram", 1, gap="nonsense; DROP TABLE daily", now=self.now)
        r = self.store.report(7, self.now)
        self.assertEqual((r["messages"], r["days"][-1]["gaps"]), (1, 0))

    def test_only_counts_are_stored_no_text(self):
        self.store.record("web", 1, sources=["hair-store/products-faq.md"], now=self.now)
        self.store.db.execute("PRAGMA wal_checkpoint(FULL)")
        tables = [r[0] for r in self.store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        cols = {c[1] for t in tables for c in self.store.db.execute(f"PRAGMA table_info({t})")}
        self.assertTrue(cols.isdisjoint({"question", "answer", "text", "session", "key", "contact", "name"}))

    def test_very_old_days_are_deleted(self):
        self.store.record("web", 1, now=self.now - 86400 * (metrics.KEEP_DAYS + 5))
        self.store.last_purge = 0
        self.store.record("web", 1, now=self.now)
        n = self.store.db.execute("SELECT COUNT(*) FROM daily").fetchone()[0]
        self.assertEqual(n, 1)

    def test_closed_database_never_raises(self):
        self.store.close()
        self.store.record("web", 1, now=self.now)
        self.assertIsNone(self.store.report(7, self.now))

    def test_switch_off(self):
        saved = os.environ.get("METRICS")
        os.environ["METRICS"] = "off"
        try:
            self.assertIsNone(metrics.open_default())
        finally:
            if saved is None:
                os.environ.pop("METRICS", None)
            else:
                os.environ["METRICS"] = saved


class ParseDaysTests(unittest.TestCase):
    def test_only_known_ranges(self):
        self.assertEqual([admin.parse_days(x) for x in ("7", "30", "90")], [7, 30, 90])
        for bad in ("", None, "5", "-1", "abc", "9999999999", "7; drop"):
            self.assertEqual(admin.parse_days(bad), 30)


class DashboardTests(Base):
    @classmethod
    def setUpClass(cls):
        cls.mdir = tempfile.mkdtemp()
        cls.saved_m = {k: os.environ.get(k) for k in ("METRICS", "METRICS_DIR")}
        os.environ["METRICS"], os.environ["METRICS_DIR"] = "on", cls.mdir
        super().setUpClass()
        cls.orig_build, cls.orig_index = server.build_index, server.Index

    @classmethod
    def tearDownClass(cls):
        server.build_index, server.Index = cls.orig_build, cls.orig_index
        super().tearDownClass()
        cls.app.metrics.close()
        for k, v in cls.saved_m.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(cls.mdir, ignore_errors=True)

    def logged_in(self):
        self.app.admin.fails.clear()
        self.app.admin.all_fails.clear()
        _, h, _ = self.login()
        return {"Cookie": self.cookie_of(h)}

    def page(self, path="/admin"):
        jar = self.logged_in()
        body = self.req("GET", path, headers=jar)[2]
        return jar, body

    def test_server_counts_every_answer_and_failure(self):
        before = self.app.metrics.report(7)["messages"]
        self.app.reply("web:m1", "web", "hello")
        self.app.reply("web:m1", "web", "[[boom]]")  # the model is down: the customer gets the fallback
        r = self.app.metrics.report(7)
        self.assertEqual(r["messages"], before + 2)
        self.assertGreaterEqual(r["errors"], 1)

    def test_dashboard_shows_charts_range_links_and_reindex_button(self):
        self.app.reply("web:m2", "web", "hello again")
        _, body = self.page()
        self.assertIn("Messages per day", body)
        self.assertIn("<svg", body)
        self.assertIn('href="/admin?days=7"', body)
        self.assertIn("Re-index now", body)
        self.assertEqual(len(re.findall(r"<script", body, re.I)), 0)
        self.assertNotRegex(body, r"\son[a-z]+=")  # no inline event handlers anywhere

    def test_range_selector_marks_the_chosen_range(self):
        _, body = self.page("/admin?days=7")
        self.assertIn("last 7 days", body)
        _, body = self.page("/admin?days=bogus")
        self.assertIn("last 30 days", body)

    def test_file_names_in_activity_are_escaped(self):
        evil = '<script>alert(1)</script>.md'
        self.app.metrics.record("web", 1, sources=[evil])
        _, body = self.page()
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;.md", body)
        self.assertEqual(len(re.findall(r"<script", body, re.I)), 0)

    # --- the re-index button
    def csrf(self, body):
        return re.search(r'action="/admin/reindex"><input type="hidden" name="csrf" value="([^"]+)"', body).group(1)

    def test_reindex_needs_login_token_and_same_site(self):
        self.assertEqual(self.req("POST", "/admin/reindex", {"csrf": "x"})[0], 403)  # not logged in
        jar, body = self.page()
        self.assertEqual(self.req("POST", "/admin/reindex", {}, jar)[0], 403)
        self.assertEqual(self.req("POST", "/admin/reindex", {"csrf": "wrong"}, jar)[0], 403)
        headers = dict(jar, Origin="https://evil.example")
        self.assertEqual(self.req("POST", "/admin/reindex", {"csrf": self.csrf(body)}, headers)[0], 403)
        self.assertEqual(self.req("GET", "/admin/reindex", headers=jar)[0], 404)  # only POST does anything

    def test_reindex_rebuilds_and_swaps_the_index_for_new_chats(self):
        calls, sentinel = [], object()

        class FakeIndex:
            @staticmethod
            def load():
                return sentinel
        server.build_index = lambda: (calls.append(1), print("Indexed 5 chunks from 2 files -> x"))[0]
        server.Index = FakeIndex
        self.app.reindex_state = {}
        jar, body = self.page()
        status, h, _ = self.req("POST", "/admin/reindex", {"csrf": self.csrf(body)}, jar)
        self.assertEqual((status, h["location"]), (303, ["/admin"]))  # answers at once: the work runs in the background
        self.app.reindex_thread.join(10)
        self.assertEqual(len(calls), 1)
        self.assertIs(self.app.sessions.index, sentinel)
        self.assertTrue(self.app.reindex_state["ok"])
        self.assertIn("Indexed 5 chunks from 2 files", self.page()[1])  # the result is shown on the page

    def test_failed_reindex_is_reported_and_keeps_the_old_index(self):
        old = self.app.sessions.index

        def boom():
            raise RuntimeError("disk full")
        server.build_index = boom
        self.app.reindex_state = {}
        ok, message = self.app.reindex()
        self.assertFalse(ok)
        self.assertIn("disk full", message)
        self.assertIs(self.app.sessions.index, old)
        self.assertIn("Re-index failed", self.page()[1])

    def test_reindex_runs_one_at_a_time_and_not_twice_in_a_row(self):
        gate, started = threading.Event(), threading.Event()

        def slow():
            started.set()
            gate.wait(5)
        server.build_index = slow
        server.Index = type("I", (), {"load": staticmethod(lambda: self.orig_index.load())})
        self.app.reindex_state = {}
        t = threading.Thread(target=self.app.reindex)
        t.start()
        self.assertTrue(started.wait(5))
        ok, message = self.app.reindex()  # a second click while the first is running
        self.assertFalse(ok)
        self.assertIn("already running", message)
        gate.set()
        t.join(10)
        ok, message = self.app.reindex()  # straight after a finished one
        self.assertFalse(ok)
        self.assertIn("just finished", message)


    def test_page_while_reindexing_refreshes_itself_and_disables_the_button(self):
        self.app.reindex_state = {"running": True, "started": time.time() - 12}
        try:
            _, body = self.page()
            self.assertIn('http-equiv="refresh"', body)
            self.assertIn("Re-indexing since", body)
            self.assertRegex(body, r"<button type=\"submit\" disabled>Re-index now")
        finally:
            self.app.reindex_state = {}
        _, body = self.page()
        self.assertNotIn('http-equiv="refresh"', body)  # normal pages do not reload

    def test_start_is_refused_while_one_is_running(self):
        self.assertTrue(self.app.reindex_lock.acquire(blocking=False))
        try:
            started, message = self.app.reindex_start()
        finally:
            self.app.reindex_lock.release()
        self.assertFalse(started)
        self.assertIn("already running", message)


class KnowledgeBaseHealthTests(unittest.TestCase):
    def test_changed_files_are_found_and_unindexed_ones_ignored(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        kb = tmp / "kb"
        (kb / "hair").mkdir(parents=True)
        (kb / "hair" / "a.md").write_text("# A\n\ntext", encoding="utf-8")
        (kb / "TODO.md").write_text("owner notes", encoding="utf-8")  # never indexed: a change here needs no re-index
        index = tmp / "chunks.json"
        index.write_text("[]", encoding="utf-8")
        old = time.time() - 3600
        for f in ((kb / "hair" / "a.md"), kb / "TODO.md", index):
            os.utime(f, (old, old))
        orig = admin.KB_DIR, admin.INDEX_PATH
        admin.KB_DIR, admin.INDEX_PATH = kb, index
        try:
            app = type("A", (), {"sessions": type("S", (), {"index": type("I", (), {"chunks": [
                {"file": "hair/a.md", "unapproved": True, "placeholders": 2}]})()})()})()
            self.assertEqual(admin.kb_health(app)["changed"], [])
            os.utime(kb / "hair" / "a.md", None)  # edited just now, after the index was written
            os.utime(kb / "TODO.md", None)
            info = admin.kb_health(app)
            self.assertEqual(info["changed"], ["hair/a.md"])
            self.assertEqual((info["chunks"], info["files"], info["unapproved"], info["placeholders"]), (1, 1, 1, 1))
        finally:
            admin.KB_DIR, admin.INDEX_PATH = orig

    def test_charts_draw_with_one_bar_and_with_none(self):
        one = admin._bars([{"day": "2026-11-05", "n": 3}], [("n", "c-main", "x")], "T")
        self.assertIn("<svg", one)
        self.assertIn("2026-11-05: 3 x", one)
        none = admin._bars([{"day": "2026-11-05", "n": 0}], [("n", "c-main", "x")], "T", "nothing here")
        self.assertNotIn("<svg class=\"plot\"", none)
        self.assertIn("nothing here", none)


if __name__ == "__main__":
    unittest.main()
