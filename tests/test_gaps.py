"""Knowledge-gap log tests. No API key, no network."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from rag import assistant, gaps
from rag.retrieve import Index


def chunk(i, text, unapproved=False):
    return {"id": i, "file": f"{i}.md", "heading": "Test", "text": text, "unapproved": unapproved, "placeholders": 0}


class MarkerTests(unittest.TestCase):
    def test_marker_is_removed_and_reported(self):
        for marker in ("[[gap]]", "[[ GAP ]]", "[[Gap]]"):
            text, marked = gaps.strip_marker(f"I don't have that detail yet.\n{marker}")
            self.assertEqual((text, marked), ("I don't have that detail yet.", True))

    def test_answer_without_marker_is_untouched(self):
        self.assertEqual(gaps.strip_marker("All fine."), ("All fine.", False))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = gaps.GapStore(self.tmp.name, daily_cap=3)

    def rows(self):
        p = Path(self.tmp.name) / "gaps.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def test_question_is_scrubbed_and_the_chat_id_is_only_stored_hashed(self):
        self.store.record("unanswered", "Do you do X? Call me on +49 176 41565516 or mail bob@example.com", "web:abcdef123456", ["a.md"])
        row = self.rows()[0]
        self.assertNotIn("bob@example.com", row["question"])
        self.assertNotIn("41565516", row["question"])
        self.assertEqual(row["session"], gaps.key_hash("web:abcdef123456"))
        self.assertNotIn("abcdef123456", json.dumps(row))

    def test_short_chatter_and_unknown_kinds_are_not_gaps(self):
        self.assertFalse(self.store.record("no_match", "hi", "k"))
        self.assertFalse(self.store.record("no_match", "ok thanks", "k"))
        self.assertTrue(self.store.record("no_match", "Do you ship?", "k"))  # short, but a real question
        self.assertFalse(self.store.record("made_up_kind", "a perfectly long question here", "k"))
        self.assertEqual([r["question"] for r in self.rows()], ["Do you ship?"])

    def test_question_is_cut_to_the_limit(self):
        self.store.record("no_match", "q" * 5000, "k")
        self.assertEqual(len(self.rows()[0]["question"]), gaps.MAX_QUESTION)

    def test_caps(self):
        for _ in range(3):
            self.assertTrue(self.store.record("no_match", "a long enough question", "k", today="2026-11-05"))
        self.assertFalse(self.store.record("no_match", "a long enough question", "k", today="2026-11-05"))
        self.assertTrue(self.store.record("no_match", "a long enough question", "k", today="2026-11-06"))
        self.store.path.write_bytes(b"x" * gaps.MAX_FILE_BYTES)
        self.assertFalse(self.store.record("no_match", "a long enough question", "k", today="2026-11-07"))

    def test_forget_removes_only_that_chats_gaps(self):
        self.store.record("no_match", "my own long question", "web:mine-0000", [])
        self.store.record("no_match", "somebody elses question", "web:other-0000", [])
        self.assertEqual(self.store.forget("web:mine-0000"), 1)
        self.assertEqual([r["question"] for r in self.rows()], ["somebody elses question"])

    def test_can_be_switched_off(self):
        os.environ["LOG_GAPS"] = "off"
        try:
            self.assertFalse(gaps.enabled())
        finally:
            os.environ.pop("LOG_GAPS", None)
        self.assertTrue(gaps.enabled())


class AssistantGapTests(unittest.TestCase):
    """The assistant must report what kind of gap a turn had, and never show the marker to the customer."""
    HOURS = chunk("hours", "We are open Monday to Friday from 8 to 18 and Saturday from 10 to 14")
    DRAFT = chunk("sla", "Response time for critical outages is 15 minutes (PROPOSED)", unapproved=True)

    def setUp(self):
        self.orig = (assistant.claude.chat, assistant.claude.create)
        self.reply = "ok"
        assistant.claude.chat = lambda *a, **k: {"stop_reason": "end_turn", "content": [{"type": "text", "text": self.reply}]}
        assistant.claude.create = lambda model, max_tokens, messages: messages[0]["content"].split("Latest message: ")[-1]
        os.environ["ANTHROPIC_API_KEY"] = "test"

    def tearDown(self):
        assistant.claude.chat, assistant.claude.create = self.orig

    def ask(self, question):
        bot = assistant.Assistant(index=Index([self.HOURS, self.DRAFT]))
        answer, _, _ = bot.ask(question)
        return bot, answer

    def test_normal_answer_is_not_a_gap(self):
        bot, _ = self.ask("When are you open on Saturday?")
        self.assertEqual(bot.gap, "")

    def test_nothing_in_the_knowledge_base_matches(self):
        bot, _ = self.ask("xqzv plorb wumble quark zint")
        self.assertEqual(bot.gap, "no_match")

    def test_only_a_hidden_draft_answers(self):
        bot, _ = self.ask("What is your response time for critical outages?")
        self.assertEqual(bot.gap, "pending")

    def test_model_says_it_does_not_know_and_the_marker_never_reaches_the_customer(self):
        self.reply = "I don't have that specific detail yet.\n[[gap]]"
        bot, answer = self.ask("When are you open on Saturday?")
        self.assertEqual(bot.gap, "unanswered")
        self.assertNotIn("[[", answer)
        self.assertEqual(bot.history[-1]["content"], answer)  # history is clean too

    def test_prompt_tells_the_model_about_the_marker(self):
        self.assertIn("[[gap]]", assistant.RUNTIME_RULES)


if __name__ == "__main__":
    unittest.main()
