"""Who is really connecting (rag/netaddr.py), and the per-visitor share of the daily message cap."""
import json
import os
import unittest

from rag import netaddr, server
from tests.test_admin import Base

LOOP = netaddr.trusted_networks("127.0.0.1,::1")


class ClientIpTests(unittest.TestCase):
    def test_a_direct_visitor_cannot_fake_their_address(self):
        self.assertEqual(netaddr.client_ip("198.51.100.5", "1.2.3.4", LOOP), "198.51.100.5")
        self.assertEqual(netaddr.client_ip("198.51.100.5", "", LOOP), "198.51.100.5")

    def test_our_proxy_is_believed(self):
        self.assertEqual(netaddr.client_ip("127.0.0.1", "203.0.113.7", LOOP), "203.0.113.7")
        self.assertEqual(netaddr.client_ip("::1", "203.0.113.7", LOOP), "203.0.113.7")
        self.assertEqual(netaddr.client_ip("127.0.0.1", "", LOOP), "127.0.0.1")

    def test_only_the_part_our_proxy_added_counts(self):
        # the visitor sent "6.6.6.6"; Caddy appended the address it really saw
        self.assertEqual(netaddr.client_ip("127.0.0.1", "6.6.6.6, 203.0.113.7", LOOP), "203.0.113.7")
        # a chain of our own proxies is skipped
        nets = netaddr.trusted_networks("127.0.0.1,10.0.0.0/8")
        self.assertEqual(netaddr.client_ip("127.0.0.1", "6.6.6.6, 203.0.113.7, 10.1.2.3", nets), "203.0.113.7")

    def test_junk_is_not_believed(self):
        for junk in ("garbage", "1.2.3.4, not-an-ip", "', DROP TABLE"):
            self.assertEqual(netaddr.client_ip("127.0.0.1", junk, LOOP), "127.0.0.1", junk)

    def test_none_means_no_proxy_and_typos_trust_nobody(self):
        self.assertEqual(netaddr.trusted_networks("none"), [])
        self.assertEqual(netaddr.trusted_networks("127.0.0.999"), [])
        self.assertEqual(netaddr.client_ip("127.0.0.1", "203.0.113.7", []), "127.0.0.1")

    def test_ipv6_and_mixed_versions(self):
        self.assertEqual(netaddr.client_ip("::1", "2001:db8::5", LOOP), "2001:db8::5")
        self.assertEqual(netaddr.client_ip("127.0.0.1", "[2001:db8::5]", LOOP), "2001:db8::5")

    def test_allow_list(self):
        self.assertTrue(netaddr.allowed("198.51.100.5", ""))                      # nothing set: no restriction
        self.assertTrue(netaddr.allowed("203.0.113.7", "203.0.113.7"))
        self.assertTrue(netaddr.allowed("10.9.9.9", "203.0.113.7, 10.0.0.0/8"))
        self.assertFalse(netaddr.allowed("198.51.100.5", "203.0.113.7"))
        self.assertFalse(netaddr.allowed("unknown", "203.0.113.7"))
        self.assertFalse(netaddr.allowed("203.0.113.7", "203.0.113.777"))        # a typo allows nobody


class DailyCapShareTests(unittest.TestCase):
    def test_one_visitor_cannot_use_up_the_day(self):
        cap = server.DailyCap(100, per_key=10)
        day = "2026-11-05"
        self.assertEqual(sum(cap.allow(day, key="ip:bot") for _ in range(50)), 10)
        self.assertEqual(cap.count, 10)  # refused messages did not use the total
        self.assertTrue(cap.allow(day, key="ip:customer"))  # everyone else is unaffected

    def test_the_total_still_applies(self):
        cap = server.DailyCap(3, per_key=2)
        results = [cap.allow("d", key=f"ip:{i}") for i in range(5)]
        self.assertEqual(results, [True, True, True, False, False])

    def test_default_share_is_ten_percent_and_the_day_resets(self):
        cap = server.DailyCap(2000)
        self.assertEqual(cap.per_key, 200)
        small = server.DailyCap(1, per_key=1)
        self.assertTrue(small.allow("d1", key="a"))
        self.assertFalse(small.allow("d1", key="a"))
        self.assertTrue(small.allow("d2", key="a"))

    def test_without_a_key_it_works_as_before(self):
        cap = server.DailyCap(2)
        self.assertEqual([cap.allow("d") for _ in range(3)], [True, True, False])

    def test_memory_is_bounded(self):
        cap = server.DailyCap(10 ** 9, per_key=5)
        cap.MAX_KEYS = 3
        for i in range(10):
            self.assertTrue(cap.allow("d", key=f"k{i}"))
        self.assertLessEqual(len(cap.keys), 3)


class ChatLimitsHttpTests(Base):
    def chat(self, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        return self.req("POST", "/api/chat", json.dumps({"message": "hello"}), h)[0]

    def with_env(self, **values):
        saved = {k: os.environ.get(k) for k in values}
        os.environ.update(values)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v) for k, v in saved.items()])

    def test_faking_the_forwarded_address_does_not_dodge_the_message_limit(self):
        self.with_env(TRUSTED_PROXIES="none")
        self.app.limiter = server.RateLimiter(3)
        codes = [self.chat({"X-Forwarded-For": f"10.0.0.{i}"}) for i in range(5)]
        self.assertEqual(codes.count(429), 2, codes)

    def test_behind_our_proxy_visitors_are_counted_separately(self):
        self.with_env(TRUSTED_PROXIES="127.0.0.1")
        self.app.limiter = server.RateLimiter(2)
        a, b = {"X-Forwarded-For": "198.51.100.1"}, {"X-Forwarded-For": "198.51.100.2"}
        self.assertEqual([self.chat(a), self.chat(a), self.chat(a)].count(429), 1)
        self.assertNotEqual(self.chat(b), 429)  # a second visitor is not blocked by the first

    def test_one_visitor_cannot_use_up_everyone_elses_daily_messages(self):
        self.with_env(TRUSTED_PROXIES="127.0.0.1")
        self.app.limiter = server.RateLimiter(1000)
        self.app.cap = server.DailyCap(100, per_key=3)
        bot = {"X-Forwarded-For": "198.51.100.66"}
        codes = [self.chat(bot) for _ in range(6)]
        self.assertEqual(codes.count(503), 3, codes)  # the bot gets the fallback after its share
        self.assertNotEqual(self.chat({"X-Forwarded-For": "203.0.113.7"}), 503)  # a customer still gets answered


if __name__ == "__main__":
    unittest.main()
