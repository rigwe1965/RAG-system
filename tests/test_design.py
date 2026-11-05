"""The chat's newer interface: which sources an answer used, the "not sure" state, and the pages that show them."""
import json
import re
import shutil
import subprocess
import unittest

from rag import server, sourcelabels
from tests.test_admin import Base

WEB = server.WEB_DIR
FILES = ["hair-store/ordering-shipping-returns.md", "hair-store/care-and-usage.md", "general/lead-qualification.md",
         "knowledge-base/TODO.md", "../secrets.md"]


class RichBot:
    """Like the real assistant for the things the page cares about: sources, a gap, a hand-off."""
    def __init__(self, *a, **k):
        self.suggestions, self.gap, self.handed_off, self.offered_booking = [], "", False, False

    def ask(self, text, note="", on_event=None):
        self.gap = "unanswered" if "unsure" in text else ""
        self.handed_off = "handoff" in text
        if "unsure" in text and self.handed_off:
            self.gap = "unanswered"
        if on_event:
            on_event("sources", sourcelabels.labels(FILES))
            on_event("text", "answer ")
            on_event("text", "text")
        return "answer text", FILES, text


class LabelTests(unittest.TestCase):
    def test_titles_come_from_the_file_headings(self):
        self.assertEqual(sourcelabels.label("hair-store/ordering-shipping-returns.md"),
                         {"line": "hair", "line_name": "Hair store", "title": "Ordering, shipping & returns"})
        self.assertEqual(sourcelabels.label("it-support-rmm/services-sla.md")["title"], "Services & SLA")
        self.assertEqual(sourcelabels.label("business-overview.md"), {"line": "general", "line_name": "Faiyke", "title": "About Faiyke"})
        self.assertEqual(sourcelabels.label("website-design/process-cost-timeline.md")["line"], "web")
        self.assertEqual(sourcelabels.label("ai-agency/ai-agent-integrations.md")["title"], "AI agent integrations")

    def test_only_customer_sources_get_a_label(self):
        for bad in ("general/voice-guidelines.md", "TODO.md", "CLAUDE.md", "../etc/passwd.md", "hair-store/x.txt", "", None, 5, ["a.md"]):
            self.assertIsNone(sourcelabels.label(bad), repr(bad))

    def test_a_few_unique_labels_and_never_a_path(self):
        out = sourcelabels.labels(FILES + ["hair-store/products-faq.md", "crm/what-we-offer.md"])
        self.assertEqual([x["title"] for x in out], ["Ordering, shipping & returns", "Care & usage", "Products & FAQ"])
        self.assertEqual(len(sourcelabels.labels(["hair-store/care-and-usage.md"] * 5)), 1)
        self.assertEqual(sourcelabels.labels(None), [])
        dumped = json.dumps(out)
        self.assertNotIn(".md", dumped)
        self.assertNotIn("hair-store/", dumped)
        for item in out:
            self.assertEqual(set(item), {"line", "line_name", "title"})
            self.assertIn(item["line"], {"hair", "ai", "web", "it", "crm", "general"})


class SourcesHttpTests(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        server.Assistant = RichBot  # Base restores the original on teardown

    def chat(self, message, path="/api/chat"):
        status, _, body = self.req("POST", path, json.dumps({"message": message}), {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        if path.endswith("/stream"):
            events = [json.loads(b[6:]) for b in body.split("\n\n") if b.startswith("data: ")]
            return events, events[-1]["done"]
        return None, json.loads(body)

    def test_answer_carries_titles_and_no_paths(self):
        _, d = self.chat("hello")
        self.assertEqual([s["title"] for s in d["sources"]], ["Ordering, shipping & returns", "Care & usage"])
        self.assertEqual(d["sources"][0]["line"], "hair")
        self.assertFalse(d["unsure"])
        raw = json.dumps(d)
        for leak in (".md", "knowledge-base", "hair-store/", "secrets", "TODO", "lead-qualification"):
            self.assertNotIn(leak, raw)

    def test_unsure_when_the_assistant_did_not_know_but_not_right_after_a_hand_off(self):
        self.assertTrue(self.chat("I am unsure")[1]["unsure"])
        self.assertFalse(self.chat("unsure handoff")[1]["unsure"])  # the customer is being passed on: no second prompt
        self.assertFalse(self.chat("hello again")[1]["unsure"])     # nothing carries over to the next answer

    def test_stream_announces_the_sources_before_the_text(self):
        events, done = self.chat("hello stream", "/api/chat/stream")
        kinds = ["src" if "src" in e else "t" if "t" in e else "done" if "done" in e else "other" for e in events]
        self.assertLess(kinds.index("src"), kinds.index("t"))
        self.assertEqual(kinds.count("src"), 1)
        src = next(e["src"] for e in events if "src" in e)
        self.assertEqual(src, done["sources"])
        self.assertNotIn("reset", {k for e in events for k in e})  # the sources event must not look like a reset

    def test_a_failed_answer_has_no_sources(self):
        class Boom(RichBot):
            def ask(self, *a, **k):
                raise RuntimeError("model down")
        server.Assistant = Boom
        try:
            _, d = self.chat("hi")
        finally:
            server.Assistant = RichBot
        self.assertEqual((d["sources"], d["unsure"]), ([], False))


class PageTests(unittest.TestCase):
    def setUp(self):
        self.html = (WEB / "index.html").read_text(encoding="utf-8")
        self.widget = (WEB / "widget.js").read_text(encoding="utf-8")

    def test_new_pieces_are_in_both_surfaces_and_both_languages(self):
        for name, text in (("page", self.html), ("widget", self.widget)):
            for needle in ("Talk to a person", "Mit einer Person sprechen", "Based on", "Grundlage", "Checking", "Ich prüfe",
                           "Wrong information", "Falsche Angabe", "cleanSources", "unsure"):
                self.assertIn(needle, text, f"{name}: {needle}")

    def test_the_old_look_is_gone(self):
        for name, text in (("page", self.html), ("widget", self.widget)):
            self.assertNotIn("typing", text.replace("typing indicator", ""), name)  # three-dot indicator
            self.assertNotIn("fy-dots", text, name)
            self.assertNotIn("#1f4e79", text, name)  # the old navy
            self.assertNotIn("#0e7c86", text, name)  # the old teal

    def test_text_from_the_server_is_never_put_in_as_html(self):
        # titles and reasons reach the page through textContent (el(...)), never innerHTML
        for text in (self.html, self.widget):
            for m in re.finditer(r"innerHTML\s*=\s*([^;\n]+)", text):
                self.assertNotRegex(m.group(1), r"\b(title|src|sources|reason|d\.|res\.)", m.group(0))

    def test_following_the_text_tells_our_scrolling_from_the_readers_by_position(self):
        """A timer-based "this scroll was automatic" flag stays on while text streams every frame, so it swallowed the
        reader's own scroll and pulled them back down (found by scrolling up in a real browser during a long answer)."""
        self.assertIn("lastTop", self.html)
        self.assertIn("Math.abs(scroller.scrollTop - lastTop) < 2", self.html)
        self.assertIsNone(re.search(r"\bauto\s*=\s*true|if \(auto\)", self.html))

    def test_motion_is_switched_off_for_people_who_ask(self):
        self.assertIn("prefers-reduced-motion: reduce", self.html)
        self.assertIn("prefers-reduced-motion:reduce", self.widget)

    def test_both_colour_schemes_are_defined(self):
        self.assertIn("prefers-color-scheme: dark", self.html)
        self.assertIn("prefers-color-scheme:dark", self.widget)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_scripts_are_valid_javascript(self):
        import tempfile
        from pathlib import Path
        script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)
        with tempfile.TemporaryDirectory() as tmp:
            for name, code in (("page.js", script), ("widget.js", self.widget)):
                p = Path(tmp) / name
                p.write_text(code, encoding="utf-8")
                r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, f"{name}: {r.stderr}")


if __name__ == "__main__":
    unittest.main()
