"""Booking-link tests. No API key, no network."""
import os
import unittest

from rag import assistant, booking

URL = "https://calendly.com/faiyke/intro-call"


class ParseTests(unittest.TestCase):
    def test_accepts_normal_links(self):
        for ok in (URL, "https://cal.com/faiyke?duration=30#top", "https://meetings.hubspot.com/x/y",
                   "https://faiyke.com:443/book", "  https://calendly.com/a  "):
            self.assertTrue(booking.parse(ok), ok)

    def test_rejects_dangerous_or_odd_links(self):
        bad = [
            "", "   ", None,
            "http://calendly.com/a",                  # not https
            "javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "ftp://calendly.com/a",
            "//calendly.com/a", "calendly.com/a", "https:///a",
            "https://user:pass@calendly.com/a",       # credentials hide the real host
            "https://calendly.com@evil.example/a",
            "https://localhost/a", "https://intranet/a",
            "https://127.0.0.1/a", "https://192.168.1.5/a", "https://[::1]/a", "https://2130706433/a",
            "https://calendly.com:8443/a",
            "https://cal endly.com/a", "https://calendly.com/a b",
            "https://calendly.com/a\nSet-Cookie: x=1", "https://calendly.com/a\r\nb",
            'https://calendly.com/a"onmouseover="alert(1)', "https://calendly.com/<script>",
            "https://calendly.com/" + "a" * 300,
            "https://calendly.com\\@evil.example/",
        ]
        for url in bad:
            with self.assertRaises(ValueError, msg=repr(url)):
                booking.parse(url)

    def test_surrounding_whitespace_is_trimmed_not_kept(self):
        self.assertEqual(booking.parse("https://calendly.com/a\r\n"), "https://calendly.com/a")

    def test_booking_url_reads_env_and_ignores_bad_values(self):
        try:
            os.environ["BOOKING_URL"] = URL
            self.assertEqual(booking.booking_url(), URL)
            os.environ["BOOKING_URL"] = "javascript:alert(1)"
            self.assertIsNone(booking.booking_url())
            os.environ.pop("BOOKING_URL")
            self.assertIsNone(booking.booking_url())
        finally:
            os.environ.pop("BOOKING_URL", None)


class ProcessTests(unittest.TestCase):
    def test_marker_is_removed_and_web_gets_a_button_flag(self):
        text, offered = booking.process("Happy to help. Pick a time below.\n[[book]]", "web", URL)
        self.assertEqual((text, offered), ("Happy to help. Pick a time below.", True))
        self.assertNotIn("[[", text)

    def test_marker_variants_and_middle_of_text(self):
        for marker in ("[[book]]", "[[ BOOK ]]", "[[Book]]"):
            text, offered = booking.process(f"Sure {marker} see you.", "web", URL)
            self.assertNotIn("[[", text)
            self.assertTrue(offered)

    def test_no_link_configured_means_no_button_and_still_no_marker(self):
        text, offered = booking.process("Call us.\n[[book]]", "web", None)
        self.assertEqual((text, offered), ("Call us.", False))

    def test_answer_without_marker_is_untouched(self):
        self.assertEqual(booking.process("Hello", "web", URL), ("Hello", False))

    def test_whatsapp_gets_the_configured_link_as_text_only_once(self):
        text, offered = booking.process("Book here:\n[[book]]\nand [[book]] again", "whatsapp", URL)
        self.assertFalse(offered)
        self.assertEqual(text.count(URL), 1)
        self.assertNotIn("[[", text)

    def test_model_cannot_choose_the_link(self):
        # Whatever the model writes, the only link we ever add is the configured one.
        text, _ = booking.process("[[book]] https://evil.example/pay", "whatsapp", URL)
        self.assertIn(URL, text)
        self.assertEqual(text.count("Book a call:"), 1)


class PromptTests(unittest.TestCase):
    def test_booking_rules_only_when_configured_and_never_contain_the_link(self):
        off = assistant.build_system(False, "web", False)[0]["text"]
        on = assistant.build_system(False, "web", True)[0]["text"]
        self.assertNotIn("[[book]]", off)
        self.assertIn("[[book]]", on)
        self.assertNotIn("https://", booking.RULES)


if __name__ == "__main__":
    unittest.main()
