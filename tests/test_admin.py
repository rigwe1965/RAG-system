"""Admin dashboard tests: login protection, cookies, and that customer text can never run code."""
import http.client
import json
import os
import re
import tempfile
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from rag import admin, feedback, gaps, server
from tests.test_server import FakeBot

PASSWORD = "correct-horse-battery-staple"
XSS = ['<script>alert(1)</script>', '"><img src=x onerror=alert(1)>', "'; DROP TABLE users; --", "<svg/onload=alert(1)>"]


class PasswordTests(unittest.TestCase):
    def test_strength_rules(self):
        self.assertEqual(admin.password_problem(PASSWORD), "")
        for bad in ("", None, "short", "a" * 30, "aaaaabbbbb", "Password1234", "administrator", "123456789012"):
            self.assertNotEqual(admin.password_problem(bad), "", repr(bad))

    def test_weak_or_missing_password_keeps_the_dashboard_off(self):
        for pw in ("", "short", "aaaaaaaaaaaaaaaa"):
            a = admin.Admin(pw)
            self.assertFalse(a.enabled)
            self.assertIsNone(a.check("anything"))
        self.assertTrue(admin.Admin(PASSWORD).enabled)

    def test_setup_makes_long_random_passwords(self):
        import secrets
        self.assertEqual(admin.password_problem(secrets.token_urlsafe(18)), "")


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.a = admin.Admin(PASSWORD)

    def test_good_and_bad_password(self):
        self.assertEqual(self.a.login("1.1.1.1", "wrong", now=0), ("bad", None))
        status, token = self.a.login("1.1.1.1", PASSWORD, now=1)
        self.assertEqual(status, "ok")
        self.assertTrue(self.a.check(token, now=2))

    def test_tokens_are_random_and_only_a_hash_is_kept(self):
        _, t1 = self.a.login("1.1.1.1", PASSWORD, now=0)
        _, t2 = self.a.login("1.1.1.1", PASSWORD, now=0)
        self.assertNotEqual(t1, t2)
        self.assertGreaterEqual(len(t1), 40)
        self.assertNotIn(t1, self.a.sessions)
        self.assertNotIn(t1, json.dumps(list(self.a.sessions)))

    def test_lockout_after_repeated_failures_even_for_the_right_password(self):
        for i in range(admin.PER_ADDRESS_MAX):
            self.assertEqual(self.a.login("9.9.9.9", "nope", now=i)[0], "bad")
        status, wait = self.a.login("9.9.9.9", PASSWORD, now=10)
        self.assertEqual(status, "locked")
        self.assertGreater(wait, 0)
        self.assertEqual(self.a.login("2.2.2.2", PASSWORD, now=10)[0], "ok")  # another address is not affected
        self.assertEqual(self.a.login("9.9.9.9", PASSWORD, now=admin.WINDOW + 10)[0], "ok")  # and the lock expires

    def test_overall_limit_stops_attacks_from_many_addresses(self):
        for i in range(admin.OVERALL_MAX):
            self.a.login(f"10.0.0.{i}", "nope", now=i)
        self.assertEqual(self.a.login("203.0.113.7", PASSWORD, now=100)[0], "locked")
        self.assertEqual(self.a.login("203.0.113.7", PASSWORD, now=admin.WINDOW + 100)[0], "ok")

    def test_sessions_expire_when_idle_and_after_the_maximum_age(self):
        _, token = self.a.login("1.1.1.1", PASSWORD, now=0)
        self.assertTrue(self.a.check(token, now=admin.IDLE_SECONDS - 1))
        self.assertIsNone(self.a.check(token, now=admin.IDLE_SECONDS - 1 + admin.IDLE_SECONDS + 5))
        _, token = self.a.login("1.1.1.1", PASSWORD, now=0)
        t = 0
        while t < admin.MAX_SECONDS:  # stays busy, so never idle ...
            t += admin.IDLE_SECONDS // 2
            self.assertTrue(self.a.check(token, now=t))
        self.assertIsNone(self.a.check(token, now=t + 1))  # ... but still ends at the maximum age

    def test_logout_ends_the_session(self):
        _, token = self.a.login("1.1.1.1", PASSWORD, now=0)
        self.a.logout(token)
        self.assertIsNone(self.a.check(token, now=1))

    def test_unknown_or_empty_tokens_are_rejected_and_old_sessions_are_evicted(self):
        self.assertIsNone(self.a.check("garbage"))
        self.assertIsNone(self.a.check(""))
        tokens = [self.a.login("1.1.1.1", PASSWORD, now=i)[1] for i in range(admin.MAX_SESSIONS + 3)]
        self.assertLessEqual(len(self.a.sessions), admin.MAX_SESSIONS)
        self.assertIsNone(self.a.check(tokens[0], now=100))
        self.assertTrue(self.a.check(tokens[-1], now=100))


class CookieTests(unittest.TestCase):
    def test_flags(self):
        c = admin.cookie_header("tok", secure=False)
        for part in ("fy_admin=tok", "HttpOnly", "SameSite=Strict", "Path=/admin"):
            self.assertIn(part, c)
        self.assertNotIn("Secure", c)
        self.assertIn("Secure", admin.cookie_header("tok", secure=True))
        self.assertIn("Max-Age=0", admin.cookie_header("", secure=False, clear=True))

    def test_reading_the_cookie_is_forgiving(self):
        self.assertEqual(admin.token_from_cookie_header("a=1; fy_admin=abc; b=2"), "abc")
        for junk in ("", None, "garbage", ";;;", "fy_admin"):
            self.assertEqual(admin.token_from_cookie_header(junk), "")


class Base(unittest.TestCase):
    """A real server with the dashboard on, talking over real HTTP."""
    password = PASSWORD

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.env = {"FEEDBACK_DIR": str(root / "fb"), "GAPS_DIR": str(root / "gaps"), "HANDOFF_DIR": str(root / "ho"),
                   "ALLOWED_ORIGINS": "https://faiyke.example", "EMBEDDINGS": "off", "ADMIN_PASSWORD": cls.password}
        cls.saved = {k: os.environ.get(k) for k in cls.env}
        os.environ.update({k: v for k, v in cls.env.items() if v})
        if not cls.password:
            os.environ.pop("ADMIN_PASSWORD", None)
        cls.orig = server.Assistant
        server.Assistant = FakeBot
        cls.root = root
        cls.app = server.App()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(cls.app))
        cls.port = cls.httpd.server_port
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.orig_delay, admin.FAIL_DELAY = admin.FAIL_DELAY, 0

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        server.Assistant = cls.orig
        admin.FAIL_DELAY = cls.orig_delay
        for k, v in cls.saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        cls.tmp.cleanup()

    def req(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        if isinstance(body, dict):
            body = urllib.parse.urlencode(body)
            h.setdefault("Content-Type", "application/x-www-form-urlencoded")
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        data = r.read().decode("utf-8", "replace")
        headers_out = {}
        for k, v in r.getheaders():
            headers_out.setdefault(k.lower(), []).append(v)
        conn.close()
        return r.status, headers_out, data

    def login(self, password=PASSWORD, extra=None):
        return self.req("POST", "/admin/login", {"password": password}, extra)

    def cookie_of(self, headers):
        return headers["set-cookie"][0].split(";")[0]


class DisabledTests(Base):
    password = ""

    def test_everything_under_admin_is_not_found_while_off(self):
        self.assertFalse(self.app.admin.enabled)
        self.assertEqual(self.req("GET", "/admin")[0], 404)
        self.assertEqual(self.req("GET", "/admin/")[0], 404)
        self.assertEqual(self.login()[0], 404)
        self.assertEqual(self.req("POST", "/admin/logout", {"csrf": "x"})[0], 404)


class AdminHttpTests(Base):
    def test_login_page_shows_no_data_and_has_strict_headers(self):
        status, h, body = self.req("GET", "/admin", headers={"Origin": "https://faiyke.example"})
        self.assertEqual(status, 200)
        self.assertIn("Log in", body)
        self.assertNotIn("Latest handoffs", body)
        self.assertEqual(h["cache-control"], ["no-store"])
        self.assertEqual(h["x-frame-options"], ["DENY"])
        self.assertIn("default-src 'none'", h["content-security-policy"][0])
        self.assertNotIn("script-src", h["content-security-policy"][0])  # nothing may run script here
        self.assertIn("noindex", h["x-robots-tag"][0])
        self.assertNotIn("access-control-allow-origin", h)  # no CORS even for an allowed website

    def test_wrong_password_gets_no_cookie(self):
        status, h, body = self.login("not-the-password")
        self.assertEqual(status, 401)
        self.assertNotIn("set-cookie", h)
        self.assertIn("Wrong password", body)

    def test_login_then_dashboard_then_logout(self):
        status, h, _ = self.login()
        self.assertEqual((status, h["location"]), (303, ["/admin"]))
        cookie = h["set-cookie"][0]
        for part in ("HttpOnly", "SameSite=Strict", "Path=/admin"):
            self.assertIn(part, cookie)
        jar = {"Cookie": self.cookie_of(h)}
        status, _, body = self.req("GET", "/admin", headers=jar)
        self.assertIn("Faiyke assistant · Admin", body)
        csrf = re.search(r'name="csrf" value="([^"]+)"', body).group(1)
        # logging out needs the secret token, and a missing or wrong one changes nothing
        self.assertEqual(self.req("POST", "/admin/logout", {"csrf": "wrong"}, jar)[0], 403)
        self.assertEqual(self.req("POST", "/admin/logout", {}, jar)[0], 403)
        self.assertIn("Faiyke assistant · Admin", self.req("GET", "/admin", headers=jar)[2])
        status, h, _ = self.req("POST", "/admin/logout", {"csrf": csrf}, jar)
        self.assertEqual(status, 303)
        self.assertIn("Max-Age=0", h["set-cookie"][0])
        self.assertIn("Log in", self.req("GET", "/admin", headers=jar)[2])  # the old cookie is dead on the server

    def test_forged_or_foreign_cookie_is_not_a_login(self):
        self.assertIn("Log in", self.req("GET", "/admin", headers={"Cookie": "fy_admin=not-a-real-token"})[2])

    def test_cross_site_login_is_refused(self):
        self.assertEqual(self.login(extra={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.login(extra={"Origin": "https://faiyke.example"})[0], 403)  # even an allowed website

    def test_big_bodies_and_unknown_paths(self):
        self.assertEqual(self.req("POST", "/admin/login", {"password": "x" * 5000})[0], 413)
        self.assertEqual(self.req("GET", "/admin/export")[0], 404)
        self.assertEqual(self.req("GET", "/admin/../etc/passwd")[0], 404)
        self.assertEqual(self.req("POST", "/admin/delete", {"x": "y"})[0], 404)

    def with_env(self, **values):
        saved = {k: os.environ.get(k) for k in values}
        os.environ.update(values)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v) for k, v in saved.items()])

    def test_lockout_cannot_be_dodged_by_faking_the_forwarded_address(self):
        """Nothing sits in front of the server: X-Forwarded-For comes from the visitor and must be ignored."""
        self.with_env(TRUSTED_PROXIES="none")
        a = self.app.admin
        a.fails.clear(); a.all_fails.clear()
        try:
            codes = [self.login("wrong", {"X-Forwarded-For": f"10.1.1.{i}"})[0] for i in range(admin.PER_ADDRESS_MAX)]
            self.assertEqual(codes, [401] * admin.PER_ADDRESS_MAX)
            status, h, _ = self.login(PASSWORD, {"X-Forwarded-For": "10.9.9.9"})  # right password, new fake address
            self.assertEqual(status, 429)
            self.assertIn("retry-after", h)
        finally:
            a.fails.clear(); a.all_fails.clear()

    def test_behind_our_proxy_each_visitor_has_their_own_lockout(self):
        """Behind Caddy every connection comes from 127.0.0.1. An attacker's failures must not lock the owner out."""
        self.with_env(TRUSTED_PROXIES="127.0.0.1,::1")
        a = self.app.admin
        a.fails.clear(); a.all_fails.clear()
        try:
            attacker = {"X-Forwarded-For": "198.51.100.66"}
            codes = [self.login("wrong", attacker)[0] for _ in range(admin.PER_ADDRESS_MAX + 1)]
            self.assertEqual(codes[-1], 429)  # the attacker is locked out
            status, _, _ = self.login(PASSWORD, {"X-Forwarded-For": "203.0.113.7"})  # the owner, from another address
            self.assertEqual(status, 303)
            # a fake address added by the visitor in front of the one Caddy appended changes nothing
            status, _, _ = self.login(PASSWORD, {"X-Forwarded-For": "203.0.113.99, 198.51.100.66"})
            self.assertEqual(status, 429)
        finally:
            a.fails.clear(); a.all_fails.clear()

    def test_admin_can_be_limited_to_listed_addresses(self):
        self.with_env(TRUSTED_PROXIES="127.0.0.1", ADMIN_ALLOWED_IPS="203.0.113.7, 10.0.0.0/8")
        self.app.admin.fails.clear()
        for ip in ("198.51.100.66", "127.0.0.1"):
            hdr = {"X-Forwarded-For": ip}
            self.assertEqual(self.req("GET", "/admin", headers=hdr)[0], 404, ip)
            self.assertEqual(self.login(extra=hdr)[0], 404, ip)  # not even the login form or a password try
        self.assertEqual(self.req("GET", "/admin", headers={"X-Forwarded-For": "203.0.113.7"})[0], 200)
        self.assertEqual(self.req("GET", "/admin", headers={"X-Forwarded-For": "10.4.5.6"})[0], 200)
        self.assertEqual(self.login(extra={"X-Forwarded-For": "203.0.113.7"})[0], 303)
        # a typo in the list allows nobody rather than everybody
        os.environ["ADMIN_ALLOWED_IPS"] = "203.0.113.777"
        self.assertEqual(self.req("GET", "/admin", headers={"X-Forwarded-For": "203.0.113.7"})[0], 404)

    def test_secure_flag_follows_https_in_front(self):
        self.app.admin.fails.clear()
        _, h, _ = self.login(extra={"X-Forwarded-Proto": "https"})
        self.assertIn("Secure", h["set-cookie"][0])

    def test_customer_text_is_escaped_everywhere_it_appears(self):
        root = self.root
        (root / "fb").mkdir(exist_ok=True); (root / "gaps").mkdir(exist_ok=True); (root / "ho").mkdir(exist_ok=True)
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        rows = [{"time": now, "rating": "down", "fid": f"{i:016x}", "session": f"s{i}", "comment": x, "question": x, "sources": [x]}
                for i, x in enumerate(XSS)]
        (root / "fb" / "feedback.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        (root / "gaps" / "gaps.jsonl").write_text("".join(
            json.dumps({"time": now, "kind": "no_match", "question": x, "sources": [x], "session": "g"}) + "\n" for x in XSS), encoding="utf-8")
        (root / "ho" / "handoffs.jsonl").write_text("".join(json.dumps(
            {"reference": x, "time": now, "priority": x, "business_line": x, "name": x, "contact": x, "summary": x, "transcript": []}) + "\n"
            for x in XSS), encoding="utf-8")
        self.app.admin.fails.clear(); self.app.admin.all_fails.clear()
        _, h, _ = self.login()
        body = self.req("GET", "/admin", headers={"Cookie": self.cookie_of(h)})[2]
        self.assertIn("Faiyke assistant · Admin", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)  # shown as text ...
        for danger in ("<script", "<img", "<svg/", "onerror=\"", "onload=\""):  # ... never as markup (the charts are our own <svg ...>)
            self.assertNotIn(danger, body, danger)
        self.assertEqual(len(re.findall(r"<script", body, re.I)), 0)

    def test_page_with_no_data_at_all_still_renders(self):
        self.app.admin.fails.clear(); self.app.admin.all_fails.clear()
        for sub in ("fb", "gaps", "ho"):
            for f in (self.root / sub).glob("*"):
                f.unlink()
        _, h, _ = self.login()
        body = self.req("GET", "/admin", headers={"Cookie": self.cookie_of(h)})[2]
        self.assertIn("No handoffs yet.", body)
        self.assertIn("Nothing yet.", body)


class GroupingTests(unittest.TestCase):
    def test_most_frequent_unanswered_question_comes_first_and_spelling_variants_are_grouped(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = gaps.GapStore(tmp.name, daily_cap=100)
        for q in ("Do you sell kids wigs?", "do you sell KIDS wigs", "Do you sell kids wigs!!", "Can you ship to Mars?"):
            store.record("unanswered", q, "web:x-0000")
        app = SimpleNamespace(cap=server.DailyCap(10), sessions=SimpleNamespace(items={}, index=SimpleNamespace(vectors=None)),
                              feedback=feedback.FeedbackStore(tmp.name), gaps=store, booking=None, privacy_url=None)
        os.environ["HANDOFF_DIR"] = tmp.name
        try:
            top = admin.collect(app)["gap_top"]
        finally:
            os.environ.pop("HANDOFF_DIR", None)
        self.assertEqual((top[0]["count"], top[1]["count"]), (3, 1))
        self.assertIn("kids wigs", top[0]["sample"].lower())


if __name__ == "__main__":
    unittest.main()
