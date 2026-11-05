"""Link allow-list, Host-header checks, the page's script policy and request-body parsing."""
import base64
import hashlib
import http.client
import json
import os
import re
import unittest

from rag import assistant, links, netaddr, server
from rag.hub import server as hub_server
from tests.test_admin import Base

WEB = server.WEB_DIR


class EnvMixin:
    def with_env(self, **values):
        saved = {k: os.environ.get(k) for k in values}
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v) for k, v in saved.items()])


class LinkTests(EnvMixin, unittest.TestCase):
    def setUp(self):
        self.with_env(BOOKING_URL=None, PRIVACY_URL=None, LINK_ALLOWED_DOMAINS=None)

    def test_our_own_addresses_stay(self):
        for text in ("See https://faiyke.com/shop for details.", "Write to https://www.faiyke.com/contact.",
                     "Open http://chat.faiyke.com/x?a=1&b=2, then ask."):
            self.assertEqual(links.clean(text), text)

    def test_other_addresses_are_removed_and_the_sentence_survives(self):
        self.assertEqual(links.clean("Pay at https://evil.example/login now."), "Pay at [link removed] now.")
        self.assertEqual(links.clean("Go to www.evil.example, quickly!"), "Go to [link removed], quickly!")
        self.assertEqual(links.clean("(https://evil.example/a)"), "([link removed])")

    def test_look_alike_hosts_are_not_ours(self):
        for bad in ("https://faiyke.com.evil.example/", "https://evilfaiyke.com/", "https://faiyke.com@evil.example/",
                    "https://faiyke.com:pw@evil.example/", "https://faiyke.co/", "https://xn--faiyke-9ua.com/",
                    "HTTPS://EVIL.EXAMPLE", "https://evil.example#faiyke.com", "https://evil.example/?u=https://faiyke.com"):
            self.assertEqual(links.clean(bad), "[link removed]", bad)

    def test_every_address_is_judged_separately(self):
        out = links.clean("https://faiyke.com/a and https://evil.example/b and www.faiyke.com")
        self.assertEqual(out, "https://faiyke.com/a and [link removed] and www.faiyke.com")

    def test_booking_privacy_and_extra_domains_come_from_your_settings(self):
        self.with_env(BOOKING_URL="https://calendly.com/faiyke/intro", PRIVACY_URL="https://example.de/datenschutz",
                      LINK_ALLOWED_DOMAINS="dhl.de, *.dhl.com")
        for ok in ("https://calendly.com/faiyke/intro", "https://example.de/datenschutz", "https://www.dhl.de/track?x=1",
                   "https://a.dhl.com/"):
            self.assertEqual(links.clean(ok), ok, ok)
        self.assertEqual(links.clean("https://other.example"), "[link removed]")

    def test_nothing_to_change(self):
        for text in ("", None, "No links here, mail info@faiyke.com or call +49 176 41565516."):
            self.assertEqual(links.clean(text), text)

    def test_the_assistants_final_answer_is_cleaned(self):
        saved = (assistant.claude.chat, assistant.claude.create)
        self.addCleanup(lambda: setattr(assistant.claude, "chat", saved[0]) or setattr(assistant.claude, "create", saved[1]))
        assistant.claude.chat = lambda **k: {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": "Please confirm your card at https://evil.example/pay or see https://faiyke.com/help"}]}
        os.environ.setdefault("ANTHROPIC_API_KEY", "test")
        answer, _, _ = assistant.Assistant().ask("how do I pay?")
        self.assertEqual(answer, "Please confirm your card at [link removed] or see https://faiyke.com/help")


class WebPageLinkTests(unittest.TestCase):
    def test_the_chat_page_only_links_hosts_on_its_list(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("linkOk(url)", html)
        self.assertIn('var LINK_HOSTS = ["faiyke.com"]', html)
        self.assertNotIn("""'$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>'""", html)  # the old unchecked version


class HostHeaderTests(EnvMixin, unittest.TestCase):
    def test_hub_accepts_only_local_names(self):
        for ok in ("127.0.0.1:8090", "localhost:8090", "localhost", "[::1]:8090", "LOCALHOST:1", "127.0.0.1"):
            self.assertTrue(hub_server.host_header_ok(ok), ok)
        for bad in ("", None, "evil.example", "evil.example:8090", "127.0.0.1.evil.example:8090", "localhost.evil.example",
                    "192.168.1.5:8090", "0.0.0.0:8090", "127.0.0.1@evil.example"):
            self.assertFalse(hub_server.host_header_ok(bad), bad)

    def test_admin_host_list(self):
        self.assertTrue(netaddr.host_allowed("anything.example", ""))  # no list: no check
        self.assertTrue(netaddr.host_allowed("chat.faiyke.com", "chat.faiyke.com, localhost"))
        self.assertTrue(netaddr.host_allowed("Chat.Faiyke.com:443", "chat.faiyke.com"))
        self.assertTrue(netaddr.host_allowed("[::1]:8080", "::1"))
        self.assertFalse(netaddr.host_allowed("evil.example", "chat.faiyke.com"))
        self.assertFalse(netaddr.host_allowed("", "chat.faiyke.com"))
        self.assertFalse(netaddr.host_allowed("chat.faiyke.com.evil.example", "chat.faiyke.com"))


class AdminHostHttpTests(EnvMixin, Base):
    def test_admin_is_not_found_under_a_name_that_is_not_listed(self):
        self.with_env(ALLOWED_HOSTS="chat.faiyke.com", ADMIN_ALLOWED_IPS=None)
        self.app.admin.fails.clear()
        self.assertEqual(self.req("GET", "/admin", headers={"Host": "rebind.evil.example"})[0], 404)
        self.assertEqual(self.login(extra={"Host": "rebind.evil.example", "Origin": "http://rebind.evil.example"})[0], 404)
        self.assertEqual(self.req("GET", "/admin", headers={"Host": "chat.faiyke.com"})[0], 200)


class PageScriptPolicyTests(unittest.TestCase):
    def test_hash_of_each_inline_script_is_listed(self):
        html = b"<html><script>var a=1;</script><script src='/x.js'></script><SCRIPT type='module'>b()</SCRIPT></html>"
        csp = server.page_csp(html)
        for body in (b"var a=1;", b"b()"):
            self.assertIn("'sha256-" + base64.b64encode(hashlib.sha256(body).digest()).decode() + "'", csp)
        self.assertEqual(csp.count("sha256-"), 2)  # the external script is not hashed

    def test_windows_line_endings_are_hashed_the_way_browsers_see_them(self):
        """Browsers normalise CRLF to LF before checking an inline script against its hash. Hashing the raw CRLF bytes
        blocked the whole chat page in a real browser (found by loading it in Chrome, not by the tests)."""
        crlf = b"<script>\r\nvar a = 1;\r\nvar b = 2;\r\n</script>"
        lf = crlf.replace(b"\r\n", b"\n")
        self.assertEqual(server.page_csp(crlf), server.page_csp(lf))
        expected = "'sha256-" + base64.b64encode(hashlib.sha256(b"\nvar a = 1;\nvar b = 2;\n").digest()).decode() + "'"
        self.assertIn(expected, server.page_csp(crlf))
        self.assertEqual(server.page_csp(b"<script>a\rb</script>"), server.page_csp(b"<script>a\nb</script>"))

    def test_no_unsafe_inline_for_scripts_and_the_other_rules_remain(self):
        csp = server.page_csp((WEB / "index.html").read_bytes())
        script_src = re.search(r"script-src ([^;]*)", csp).group(1)
        self.assertNotIn("unsafe-inline", script_src)
        self.assertNotIn("unsafe-eval", csp)
        for part in ("default-src 'self'", "frame-ancestors 'none'", "base-uri 'none'", "object-src 'none'", "connect-src 'self'"):
            self.assertIn(part, csp)

    def test_the_real_pages_work_under_their_policy(self):
        """Every inline script is covered by a hash, and nothing needs a blocked feature (inline handlers, javascript:)."""
        for name in ("index.html", "cookies.html"):
            html = (WEB / name).read_bytes()
            scripts = INLINE.findall(html)
            self.assertEqual(server.page_csp(html).count("sha256-"), len(scripts), name)
            self.assertIsNone(re.search(rb"(?i)<[^>]+\son[a-z]+\s*=", html), f"{name} has an inline event handler")
            self.assertNotIn(b"javascript:", html.lower(), name)
        self.assertNotIn("eval(", (WEB / "index.html").read_text(encoding="utf-8"))
        self.assertNotIn("new Function", (WEB / "index.html").read_text(encoding="utf-8"))


INLINE = server.INLINE_SCRIPT


class PageHttpTests(Base):
    def test_page_is_served_with_the_hashed_policy(self):
        status, h, body = self.req("GET", "/")
        self.assertEqual(status, 200)
        csp = h["content-security-policy"][0]
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)
        inline = INLINE.findall(body.encode("utf-8"))
        self.assertEqual(len(inline), 1)
        seen_by_browser = inline[0].replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        self.assertIn("sha256-" + base64.b64encode(hashlib.sha256(seen_by_browser).digest()).decode(), csp)


class BodyParsingTests(Base):
    def raw(self, content_length, body=b""):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("POST", "/api/chat")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", content_length)
        conn.endheaders(body)
        try:
            r = conn.getresponse()
            return r.status
        finally:
            conn.close()

    def test_bad_content_length_is_a_clean_error_not_a_hang_or_crash(self):
        for value in ("abc", "-5", "", "1e3"):
            self.assertIn(self.raw(value), (400, 411), value)  # answered quickly with an error, thread not stuck
        self.assertEqual(self.req("GET", "/health")[0], 200)  # and the server is still fine

    def test_normal_requests_still_work(self):
        payload = json.dumps({"message": "hello"}).encode()
        self.assertEqual(self.raw(str(len(payload)), payload), 200)


if __name__ == "__main__":
    unittest.main()
