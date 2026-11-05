"""Server tests. No API key, no network, no real WhatsApp."""
import hashlib
import hmac
import json
import os
import tempfile
import threading
from pathlib import Path
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from rag import feedback, server


class FakeBot:
    def __init__(self, *a, **k):
        self.seen = []

    def ask(self, text, note="", on_event=None):
        self.seen.append((text, note))
        self.offered_booking = "[[book]]" in text  # the real Assistant strips the marker the same way
        if "[[boom]]" in text:
            raise RuntimeError("the model is down")
        self.suggestions = ["What does it cost?", "How long does it take?"] if "[[next]]" in text else []
        answer = f"echo: {text}".replace("[[book]]", "").replace("[[next]]", "").strip()
        if on_event:  # stream it in small pieces, like the real Assistant
            for i in range(0, len(answer), 4):
                on_event("text", answer[i:i + 4])
        return answer, [], text


class HelperTests(unittest.TestCase):
    def test_signature_valid_and_invalid(self):
        body = b'{"a":1}'
        good = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(server.verify_signature("secret", body, good))
        self.assertFalse(server.verify_signature("secret", body, "sha256=deadbeef"))
        self.assertFalse(server.verify_signature("secret", body, None))
        self.assertFalse(server.verify_signature("", body, good))  # no secret configured = reject

    def test_parse_whatsapp(self):
        payload = {"entry": [{"changes": [{"value": {"messages": [
            {"id": "m1", "from": "49123", "type": "text", "text": {"body": "Hallo"}},
            {"id": "m2", "from": "49123", "type": "image"},
        ]}}]}]}
        self.assertEqual(server.parse_whatsapp(payload), [("m1", "49123", "Hallo"), ("m2", "49123", None)])
        self.assertEqual(server.parse_whatsapp({"entry": [{"changes": [{"value": {"statuses": []}}]}]}), [])

    def test_split_message(self):
        text = ("word " * 2000).strip()
        parts = server.split_message(text, limit=500)
        self.assertTrue(all(len(p) <= 500 for p in parts))
        self.assertEqual(" ".join(parts).split(), text.split())

    def test_rate_limiter(self):
        rl = server.RateLimiter(2)
        self.assertTrue(rl.allow("a", now=0))
        self.assertTrue(rl.allow("a", now=1))
        self.assertFalse(rl.allow("a", now=2))
        self.assertTrue(rl.allow("b", now=2))
        self.assertTrue(rl.allow("a", now=70))

    def test_daily_cap(self):
        cap = server.DailyCap(1)
        self.assertTrue(cap.allow("2026-11-04"))
        self.assertFalse(cap.allow("2026-11-04"))
        self.assertTrue(cap.allow("2026-11-05"))

    def test_sessions_expire_and_are_separate(self):
        orig = server.Assistant
        server.Assistant = FakeBot
        try:
            s = server.Sessions(index=None)
            a, _, new_a = s.get("x", "web", now=0)
            b, _, _ = s.get("y", "web", now=1)
            a2, _, new_again = s.get("x", "web", now=10)
            self.assertTrue(new_a)
            self.assertFalse(new_again)
            self.assertIs(a, a2)
            self.assertIsNot(a, b)
            a3, _, renewed = s.get("x", "web", now=10 + server.SESSION_TTL + 1)
            self.assertTrue(renewed)
            self.assertIsNot(a, a3)
        finally:
            server.Assistant = orig


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig = server.Assistant
        server.Assistant = FakeBot
        os.environ["ALLOWED_ORIGINS"] = "https://faiyke.example"
        os.environ["WHATSAPP_VERIFY_TOKEN"] = "vt"
        os.environ["WHATSAPP_APP_SECRET"] = "secret"
        cls.fb_tmp = tempfile.TemporaryDirectory()
        os.environ["FEEDBACK_DIR"] = cls.fb_tmp.name
        os.environ["FEEDBACK_RATE_PER_MIN"] = "1000"
        os.environ["FORGET_RATE_PER_MIN"] = "1000"
        cls.app = server.App()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(cls.app))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        server.Assistant = cls.orig
        for k in ("ALLOWED_ORIGINS", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET", "FEEDBACK_DIR", "FEEDBACK_RATE_PER_MIN", "FORGET_RATE_PER_MIN"):
            os.environ.pop(k, None)
        cls.fb_tmp.cleanup()

    def call(self, path, data=None, headers=None, method=None):
        body = json.dumps(data).encode() if isinstance(data, dict) else data
        req = urllib.request.Request(self.base + path, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), dict(e.headers)

    def test_health_and_widget(self):
        self.assertEqual(self.call("/health")[0], 200)
        status, body, _ = self.call("/widget.js")
        self.assertEqual(status, 200)
        self.assertIn("/api/chat", body)

    def test_cookie_policy_page_and_banner(self):
        status, body, headers = self.call("/cookies")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("Content-Security-Policy", headers)
        self.assertNotIn("<script", body)                      # the policy page runs no code
        # every item the chat page may store is listed, in both languages
        for name in ("faiyke_cookie_choice", "faiyke_chats_v1", "faiyke_lang", "faiyke_voice_ok", "faiyke_autoread", "faiyke_session"):
            self.assertEqual(body.count(name), 2, name)
        page = self.call("/")[1]
        for needle in ('id="cookieBar"', 'id="cookieYes"', 'id="cookieNo"', 'href="/cookies"', 'id="cookieSettings"'):
            self.assertIn(needle, page)

    def test_page_stores_optional_items_only_through_the_consent_gate(self):
        import re
        page = self.call("/")[1]
        # outside the three small helpers, the chat page must not write or read localStorage directly
        direct = [m.group(0) for m in re.finditer(r"localStorage\.\w+\(([^)]*)\)", page)]
        allowed = {"localStorage.getItem(CHOICE)", "localStorage.getItem(k)", "localStorage.setItem(k, v)", "localStorage.removeItem(k)",
                   "localStorage.setItem(CHOICE, value)", 'localStorage.removeItem(STORE)', 'localStorage.removeItem("faiyke_voice_ok")',
                   'localStorage.removeItem("faiyke_autoread")'}
        self.assertEqual([d for d in direct if d not in allowed], [])
        self.assertIn('data-optional-storage="off"', self.call("/widget.js")[1])

    def test_chat_round_trip_keeps_session(self):
        code, body, _ = self.call("/api/chat", {"message": "hello"}, {"Content-Type": "application/json"})
        data = json.loads(body)
        self.assertEqual((code, data["reply"]), (200, "echo: hello"))
        code, body, _ = self.call("/api/chat", {"message": "again", "session_id": data["session_id"]})
        self.assertEqual(json.loads(body)["session_id"], data["session_id"])

    def test_chat_rejects_bad_input(self):
        self.assertEqual(self.call("/api/chat", {"message": ""})[0], 400)
        self.assertEqual(self.call("/api/chat", {"message": "x" * 1001})[0], 400)
        self.assertEqual(self.call("/api/chat", b"not json")[0], 400)

    def test_chat_blocks_unknown_origin_and_allows_listed(self):
        self.assertEqual(self.call("/api/chat", {"message": "hi"}, {"Origin": "https://evil.example"})[0], 403)
        code, _, headers = self.call("/api/chat", {"message": "hi"}, {"Origin": "https://faiyke.example"})
        self.assertEqual(code, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "https://faiyke.example")

    def test_config_exposes_only_the_booking_link(self):
        original = self.app.booking
        try:
            self.app.booking = None
            self.assertEqual(set(json.loads(self.call("/api/config")[1])), {"booking_url", "privacy_url"})  # nothing else
            self.assertIsNone(json.loads(self.call("/api/config")[1])["booking_url"])
            self.app.booking = "https://calendly.com/faiyke/intro"
            self.assertEqual(json.loads(self.call("/api/config")[1])["booking_url"], "https://calendly.com/faiyke/intro")
        finally:
            self.app.booking = original

    def test_book_flag_needs_both_the_marker_and_a_configured_link(self):
        original = self.app.booking
        try:
            self.app.booking = "https://calendly.com/faiyke/intro"
            on = json.loads(self.call("/api/chat", {"message": "call please [[book]]"})[1])
            plain = json.loads(self.call("/api/chat", {"message": "just a question"})[1])
            self.app.booking = None
            off = json.loads(self.call("/api/chat", {"message": "call please [[book]]"})[1])
        finally:
            self.app.booking = original
        self.assertTrue(on["book"])
        self.assertNotIn("[[", on["reply"])
        self.assertFalse(plain["book"])
        self.assertFalse(off["book"])

    def test_forget_erases_conversation_and_ratings_of_that_chat_only(self):
        mine = json.loads(self.call("/api/chat", {"message": "my question one"})[1])
        other = json.loads(self.call("/api/chat", {"message": "someone else"})[1])
        for chat in (mine, other):
            self.call("/api/feedback", {"session_id": chat["session_id"], "fid": chat["fid"], "rating": "down"})
        self.assertIsNotNone(self.app.sessions.find(f"web:{mine['session_id']}", mine["fid"]))
        code, body, _ = self.call("/api/forget", {"session_id": mine["session_id"]})
        self.assertEqual((code, json.loads(body)), (200, {"ok": True}))
        self.assertIsNone(self.app.sessions.find(f"web:{mine['session_id']}", mine["fid"]))
        sessions = {r["session"] for r in self.fb_rows()}
        self.assertNotIn(feedback.session_hash(mine["session_id"]), sessions)
        self.assertIn(feedback.session_hash(other["session_id"]), sessions)
        self.assertIsNotNone(self.app.sessions.find(f"web:{other['session_id']}", other["fid"]))

    def test_forget_gives_the_same_answer_for_unknown_chats_and_rejects_bad_input(self):
        self.assertEqual(self.call("/api/forget", {"session_id": "never-existed-1234"})[0], 200)
        self.assertEqual(self.call("/api/forget", {"session_id": "short"})[0], 400)
        self.assertEqual(self.call("/api/forget", {"session_id": "../../etc/passwd/xxxxx"})[0], 400)
        self.assertEqual(self.call("/api/forget", {})[0], 400)
        self.assertEqual(self.call("/api/forget", b"not json")[0], 400)
        self.assertEqual(self.call("/api/forget", {"session_id": "x" * 2000})[0], 413)

    def test_forget_blocks_unknown_origin_and_is_rate_limited(self):
        data = {"session_id": "never-existed-1234"}
        self.assertEqual(self.call("/api/forget", data, {"Origin": "https://evil.example"})[0], 403)
        original = self.app.forget_limiter
        self.app.forget_limiter = server.RateLimiter(2)
        try:
            codes = [self.call("/api/forget", data)[0] for _ in range(3)]
        finally:
            self.app.forget_limiter = original
        self.assertEqual(codes, [200, 200, 429])

    def test_config_includes_the_privacy_link(self):
        original = self.app.privacy_url
        try:
            self.app.privacy_url = "https://faiyke.com/datenschutz"
            self.assertEqual(json.loads(self.call("/api/config")[1])["privacy_url"], "https://faiyke.com/datenschutz")
            self.app.privacy_url = None
            self.assertIsNone(json.loads(self.call("/api/config")[1])["privacy_url"])
        finally:
            self.app.privacy_url = original

    def test_chat_page_has_security_headers_and_api_does_not_need_them(self):
        _, _, h = self.call("/")
        self.assertEqual(h.get("X-Frame-Options"), "DENY")
        self.assertIn("frame-ancestors 'none'", h.get("Content-Security-Policy", ""))
        self.assertIn("connect-src 'self'", h.get("Content-Security-Policy", ""))
        self.assertEqual(h.get("Referrer-Policy"), "no-referrer")

    def fb_rows(self):
        p = Path(self.fb_tmp.name) / "feedback.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def test_feedback_is_matched_to_the_answer_server_side(self):
        _, body, _ = self.call("/api/chat", {"message": "what is the price? mail me bob@example.com"})
        chat = json.loads(body)
        self.assertEqual(len(chat["fid"]), 16)
        before = len(self.fb_rows())
        code, body, _ = self.call("/api/feedback", {"session_id": chat["session_id"], "fid": chat["fid"],
                                                    "rating": "down", "comment": "wrong"})
        self.assertEqual((code, json.loads(body)), (200, {"ok": True}))
        row = self.fb_rows()[before]
        self.assertIn("what is the price", row["question"])
        self.assertNotIn("bob@example.com", row["question"])
        self.assertNotIn(chat["session_id"], json.dumps(row))

    def test_feedback_for_unknown_session_is_stored_without_context(self):
        before = len(self.fb_rows())
        code, _, _ = self.call("/api/feedback", {"session_id": "not-a-real-session-id", "fid": "0123456789abcdef", "rating": "down"})
        self.assertEqual(code, 200)
        self.assertIsNone(self.fb_rows()[before]["question"])

    def test_feedback_rejects_bad_input_and_big_bodies(self):
        self.assertEqual(self.call("/api/feedback", {"rating": "meh", "fid": "0123456789abcdef"})[0], 400)
        self.assertEqual(self.call("/api/feedback", {"rating": "up", "fid": "nope"})[0], 400)
        self.assertEqual(self.call("/api/feedback", b"not json")[0], 400)
        self.assertEqual(self.call("/api/feedback", b"[1,2]")[0], 400)
        self.assertEqual(self.call("/api/feedback", {"rating": "up", "fid": "0123456789abcdef", "comment": "x" * 5000})[0], 413)

    def test_feedback_blocks_unknown_origin(self):
        data = {"rating": "up", "fid": "0123456789abcdef"}
        self.assertEqual(self.call("/api/feedback", data, {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.call("/api/feedback", data, {"Origin": "https://faiyke.example"})[0], 200)

    def test_feedback_is_rate_limited(self):
        original = self.app.fb_limiter
        self.app.fb_limiter = server.RateLimiter(2)
        try:
            data = {"rating": "up", "fid": "0123456789abcdef"}
            codes = [self.call("/api/feedback", data)[0] for _ in range(3)]
        finally:
            self.app.fb_limiter = original
        self.assertEqual(codes, [200, 200, 429])

    def test_whatsapp_verification(self):
        q = "?hub.mode=subscribe&hub.verify_token=vt&hub.challenge=12345"
        self.assertEqual(self.call("/webhook/whatsapp" + q)[:2], (200, "12345"))
        self.assertEqual(self.call("/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=no&hub.challenge=1")[0], 403)

    def test_whatsapp_rejects_unsigned_post(self):
        self.assertEqual(self.call("/webhook/whatsapp", {"entry": []})[0], 403)

    def test_whatsapp_accepts_signed_post(self):
        body = json.dumps({"entry": []}).encode()
        sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        self.assertEqual(self.call("/webhook/whatsapp", body, {"X-Hub-Signature-256": sig})[0], 200)

    def test_whatsapp_flow_sends_disclosure_then_answer(self):
        sent = []
        orig = server.send_whatsapp
        server.send_whatsapp = lambda to, text: sent.append((to, text))
        try:
            payload = {"entry": [{"changes": [{"value": {"messages": [
                {"id": "wamid.1", "from": "491234", "type": "text", "text": {"body": "Hi"}}]}}]}]}
            self.app.handle_whatsapp(payload)
            self.app.handle_whatsapp(payload)  # Meta retry must be ignored
        finally:
            server.send_whatsapp = orig
        self.assertEqual(sent, [("491234", server.DISCLOSURE), ("491234", "echo: Hi")])


if __name__ == "__main__":
    unittest.main()
