"""Retrieval tests. They need no API key.   Run:  python -m unittest discover -s tests -t ."""
import unittest

from rag.ingest import build_chunks
from rag.retrieve import Index


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = build_chunks()
        cls.index = Index(cls.chunks)

    def files(self, query, **kw):
        return [c["file"] for _, c in self.index.search(query, **kw)]

    def test_meta_files_and_todo_not_indexed(self):
        files = {c["file"] for c in self.chunks}
        self.assertNotIn("TODO.md", files)
        self.assertNotIn("CLAUDE.md", files)
        self.assertNotIn("general/voice-guidelines.md", files)

    def test_opening_hours(self):
        self.assertIn("business-overview.md", self.files("what are your opening hours"))

    def test_hair_returns(self):
        got = self.files("can I return my wig after wearing it", include_drafts=True)
        self.assertIn("hair-store/ordering-shipping-returns.md", got[:3])

    def test_bundle_quantity(self):
        got = self.files("how many bundles do I need for 22 inch", include_drafts=True)
        self.assertIn("hair-store/sizing-quantity.md", got[:3])

    def test_agent_integrations(self):
        got = self.files("can an AI agent connect to HubSpot and create tickets")
        self.assertTrue(any(f in ("ai-agency/ai-agent-integrations.md", "crm/what-we-offer.md") for f in got[:3]))

    def test_rmm_tools(self):
        self.assertIn("it-support-rmm/remote-management.md", self.files("remote monitoring patch management agent"))

    def synthetic_index(self):
        def chunk(i, text, unapproved):
            return {"id": i, "file": f"{i}.md", "heading": "Test", "text": text,
                    "unapproved": unapproved, "placeholders": 0}
        return Index([
            chunk("draft", "response time for outages is 15 minutes (PROPOSED)", True),
            chunk("final", "response time for outages is one hour", False),
        ])

    def test_drafts_hidden_by_default(self):
        hits = self.synthetic_index().search("response time outages", min_score=0)
        self.assertEqual([c["id"] for _, c in hits], ["final"])

    def test_drafts_visible_when_allowed(self):
        hits = self.synthetic_index().search("response time outages", include_drafts=True, min_score=0)
        self.assertEqual({c["id"] for _, c in hits}, {"draft", "final"})

    def test_nonsense_returns_nothing(self):
        self.assertEqual(self.index.search("xqzv plorb wumble"), [])


if __name__ == "__main__":
    unittest.main()
