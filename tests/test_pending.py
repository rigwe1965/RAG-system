"""Tests for "the answer exists but is still a hidden draft (PROPOSED)". No API key, no network."""
import json
import os
import unittest

from rag import assistant, embed
from rag.retrieve import Index


def chunk(i, text, unapproved=False, file=None):
    return {"id": i, "file": file or f"{i}.md", "heading": "Test", "text": text, "unapproved": unapproved, "placeholders": 0}


class FakeVectors:
    def __init__(self, sims):
        self.sims = sims

    def scores(self, query):
        return self.sims


DRAFT = chunk("sla", "Response time for critical outages is 15 minutes (PROPOSED)", unapproved=True)
HOURS = chunk("hours", "We are open Monday to Friday from 8 to 18 and Saturday from 10 to 14")
SHIP = chunk("ship", "Shipping inside Germany takes three days with tracking")


class KeywordPathTests(unittest.TestCase):
    def setUp(self):
        self.index = Index([DRAFT, HOURS, SHIP])

    def test_notice_when_only_a_draft_answers(self):
        self.assertEqual(assistant.pending_for(self.index, "what is the response time for critical outages"), assistant.PENDING_NOTICE)

    def test_no_notice_when_an_approved_passage_answers(self):
        self.assertEqual(assistant.pending_for(self.index, "when are you open on Saturday"), "")

    def test_no_notice_without_any_draft(self):
        idx = Index([{**DRAFT, "unapproved": False, "text": "Response time for critical outages is one hour"}, HOURS])
        self.assertEqual(assistant.pending_for(idx, "what is the response time for critical outages"), "")

    def test_any_of_several_queries_can_trigger_it(self):
        self.assertEqual(assistant.pending_for(self.index, "something unrelated here", "critical outages response time"),
                         assistant.PENDING_NOTICE)


class SemanticPathTests(unittest.TestCase):
    """By meaning (for example a German question). Chunk order: draft, approved, approved."""
    chunks = [chunk("d", "alpha (PROPOSED)", True), chunk("a", "beta"), chunk("b", "gamma")]

    def wins(self, sims, chunks=None):
        return Index(chunks or self.chunks, vectors=FakeVectors(sims)).semantic_draft_wins("zzzz")

    def test_clear_draft_match_counts(self):
        self.assertTrue(self.wins([0.70, 0.40, 0.30]))

    def test_draft_that_is_closer_than_the_approved_text_counts_even_narrowly(self):
        self.assertTrue(self.wins([0.66, 0.65, 0.30]))

    def test_approved_text_that_fits_as_well_or_better_keeps_the_assistant_answering(self):
        self.assertFalse(self.wins([0.60, 0.60, 0.30]))
        self.assertFalse(self.wins([0.55, 0.62, 0.30]))

    def test_weak_draft_match_does_not_count(self):
        self.assertFalse(self.wins([0.30, 0.20, 0.10]))  # ahead of the others, but too weak to mean anything

    def test_approved_chunk_is_never_a_pending_draft(self):
        self.assertFalse(self.wins([0.70, 0.40, 0.30], [chunk("d", "alpha"), chunk("a", "beta"), chunk("b", "gamma")]))

    def test_no_vectors_or_failed_vectors_mean_no_opinion(self):
        self.assertFalse(Index(self.chunks).semantic_draft_wins("zzzz"))
        self.assertFalse(self.wins(None))

    def test_only_drafts_in_the_knowledge_base(self):
        self.assertTrue(self.wins([0.70], [chunk("d", "alpha (PROPOSED)", True)]))


class AssistantTurnTests(unittest.TestCase):
    """The notice must reach the model, and only when it should."""

    def setUp(self):
        self.orig = (assistant.claude.chat, assistant.claude.create)
        self.sent = []

        def fake_chat(model, messages, max_tokens=800, system=None, tools=None, timeout=60):
            self.sent.append(messages[-1]["content"])
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}
        assistant.claude.chat = fake_chat
        os.environ["ANTHROPIC_API_KEY"] = "test"

    def tearDown(self):
        assistant.claude.chat, assistant.claude.create = self.orig

    def ask(self, question, query=None, **kw):
        assistant.claude.create = lambda *a, **k: query or question
        bot = assistant.Assistant(index=Index([DRAFT, HOURS, SHIP]), **kw)
        bot.ask(question)
        return self.sent[-1]

    def test_model_is_told_when_the_only_answer_is_a_draft(self):
        turn = self.ask("What is your response time for critical outages?")
        self.assertIn("waiting for the owner's approval", turn)
        self.assertNotIn("15 minutes", turn)  # the draft text itself stays hidden

    def test_model_is_not_told_for_normal_questions(self):
        self.assertNotIn("waiting for the owner's approval", self.ask("When are you open on Saturday?"))

    def test_notice_is_skipped_in_draft_testing_mode(self):
        turn = self.ask("What is your response time for critical outages?", include_drafts=True)
        self.assertNotIn("waiting for the owner's approval", turn)
        self.assertIn("15 minutes", turn)  # testing mode may use drafts

    def test_a_search_query_alone_can_trigger_it(self):
        # the customer's own words (German) do not match, but the rewritten English query does
        turn = self.ask("Wie schnell reagiert ihr bei einem Ausfall?", query="critical outages response time")
        self.assertIn("waiting for the owner's approval", turn)


def _real_index_ready():
    try:
        import fastembed  # noqa: F401
        embed.verify_model()
        chunks = json.loads((embed.ROOT / "index" / "chunks.json").read_text(encoding="utf-8"))
        embed.check_files(chunks)
        return True
    except Exception:
        return False


@unittest.skipUnless(_real_index_ready(), "model not downloaded or vector index not built")
class RealModelTests(unittest.TestCase):
    """Real chunks and the real model. The returns page is marked as a draft in memory only."""

    @classmethod
    def setUpClass(cls):
        chunks = json.loads((embed.ROOT / "index" / "chunks.json").read_text(encoding="utf-8"))
        vectors = embed.load_vectors(chunks, quiet=True)
        for c in chunks:
            c["unapproved"] = c["file"] == "hair-store/ordering-shipping-returns.md"
        cls.index = Index(chunks, vectors=vectors)

    def test_questions_about_the_pending_page_are_caught_by_meaning_in_both_languages(self):
        for q in ("Kann ich meine Bestellung zurückschicken", "how do I get my money back",
                  "what is your refund policy", "can I cancel my order", "I received the wrong item"):
            self.assertTrue(self.index.semantic_draft_wins(q), q)

    def test_questions_about_other_pages_are_not_flagged(self):
        for q in ("Wie lange dauert eine Webseite", "how do I keep my hair from tangling",
                  "what does a customer-support chatbot cost", "what if my computers get hacked",
                  "Wann habt ihr geöffnet", "write me a poem about autumn", "which CRM fits a small team",
                  "how many bundles do I need for 22 inch", "can an AI agent connect to HubSpot",
                  "who looks after my site after launch"):
            self.assertFalse(self.index.semantic_draft_wins(q), q)
            self.assertEqual(assistant.pending_for(self.index, q), "", q)


if __name__ == "__main__":
    unittest.main()
