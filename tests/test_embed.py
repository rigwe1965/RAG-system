"""Semantic-search tests. They need no model download and no network, except the one marked."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from rag import embed
from rag.retrieve import Index

try:
    import numpy as np
except ImportError:  # numpy is part of the optional extra
    np = None


def chunk(i, text, unapproved=False, heading="Test"):
    return {"id": i, "file": f"{i}.md", "heading": heading, "text": text, "unapproved": unapproved, "placeholders": 0}


class FakeVectors:
    """Stands in for the model: returns fixed similarities per chunk."""

    def __init__(self, sims):
        self.sims = sims

    def scores(self, query):
        return self.sims


class VerifyModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        (self.dir / "a.bin").write_bytes(b"model data")
        (self.dir / "b.json").write_bytes(b"{}")
        self.pinned = {"a.bin": embed.sha256_file(self.dir / "a.bin"), "b.json": embed.sha256_file(self.dir / "b.json")}

    def test_good_files_pass(self):
        embed.verify_model(self.dir, self.pinned)

    def test_tampered_file_is_refused(self):
        (self.dir / "a.bin").write_bytes(b"model data + something extra")
        with self.assertRaises(embed.ModelError) as cm:
            embed.verify_model(self.dir, self.pinned)
        self.assertIn("pinned hash", str(cm.exception))

    def test_missing_file_is_refused(self):
        (self.dir / "b.json").unlink()
        with self.assertRaises(embed.ModelError):
            embed.verify_model(self.dir, self.pinned)

    def test_file_without_a_pinned_hash_is_refused(self):
        with self.assertRaises(embed.ModelError):
            embed.verify_model(self.dir, {**self.pinned, "b.json": ""})

    def test_real_pins_are_complete_and_well_formed(self):
        for name, h in embed.PINNED.items():
            self.assertRegex(h, r"^[0-9a-f]{64}$", name)
        self.assertRegex(embed.REVISION, r"^[0-9a-f]{40}$")


class WindowTests(unittest.TestCase):
    def test_long_chunk_is_cut_and_each_piece_keeps_the_title(self):
        text = " ".join(f"Sentence number {n} about returns and refunds." for n in range(60))
        ws = embed.windows(chunk("x", text, heading="Shop > Returns"))
        self.assertGreater(len(ws), 3)
        self.assertTrue(all(w.startswith("Returns. ") for w in ws))
        self.assertTrue(all(len(w) <= embed.WINDOW + 120 for w in ws))

    def test_short_and_empty_chunks_still_give_a_window(self):
        self.assertEqual(len(embed.windows(chunk("x", "Short text."))), 1)
        self.assertEqual(len(embed.windows(chunk("x", ""))), 1)

    def test_fingerprint_changes_with_the_text(self):
        a, b = [chunk("1", "hello")], [chunk("1", "hello!")]
        self.assertNotEqual(embed.chunks_fingerprint(a), embed.chunks_fingerprint(b))
        self.assertEqual(embed.chunks_fingerprint(a), embed.chunks_fingerprint([chunk("1", "hello")]))


@unittest.skipIf(np is None, "numpy not installed")
class SavedVectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vec, self.meta = Path(self.tmp.name) / "v.npy", Path(self.tmp.name) / "m.json"
        self.chunks = [chunk("a", "alpha"), chunk("b", "beta")]
        self.matrix = np.eye(3, 4, dtype=np.float32)
        self.owners = [0, 0, 1]
        self.write()

    def write(self, **over):
        meta = {"model": embed.MODEL_NAME, "revision": embed.REVISION, "dim": 4, "windows": 3, "chunks": 2,
                "fingerprint": embed.chunks_fingerprint(self.chunks), "owners": self.owners, **over}
        np.save(self.vec, self.matrix, allow_pickle=False)
        self.meta.write_text(json.dumps(meta), encoding="utf-8")

    def check(self, chunks=None):
        return embed.check_files(chunks or self.chunks, self.vec, self.meta)

    def test_matching_files_load(self):
        matrix, owners = self.check()
        self.assertEqual(matrix.shape, (3, 4))
        self.assertEqual(list(owners), [0, 0, 1])

    def test_changed_knowledge_base_is_detected(self):
        with self.assertRaises(embed.ModelError):
            self.check([chunk("a", "alpha"), chunk("b", "beta CHANGED")])

    def test_other_model_or_revision_is_refused(self):
        for over in ({"model": "someone/else"}, {"revision": "0" * 40}):
            self.write(**over)
            with self.assertRaises(embed.ModelError, msg=str(over)):
                self.check()

    def test_wrong_shape_or_owner_numbers_are_refused(self):
        for over in ({"windows": 5}, {"dim": 9}, {"owners": [0, 1]}, {"owners": [0, 0, 7]}, {"owners": [0, 0, -1]}):
            self.write(**over)
            with self.assertRaises(embed.ModelError, msg=str(over)):
                self.check()

    def test_file_that_needs_pickle_is_refused(self):
        evil = np.array([{"x": 1}, object()], dtype=object)
        np.save(self.vec, evil, allow_pickle=True)  # such a file could run code if loaded the unsafe way
        with self.assertRaises(embed.ModelError):
            self.check()

    def test_missing_files_are_refused(self):
        self.vec.unlink()
        with self.assertRaises(embed.ModelError):
            self.check()

    def test_corrupt_file_is_refused(self):
        self.vec.write_bytes(b"not a numpy file")
        with self.assertRaises(embed.ModelError):
            self.check()


class FusionTests(unittest.TestCase):
    """Search with fake similarities. This is where the draft-hiding rule is checked."""

    def setUp(self):
        self.chunks = [
            chunk("price", "The shipping price is five euros for orders in Germany."),
            chunk("refund", "Money is returned within 14 days after we receive the parcel."),
            chunk("draft", "Refunds are instant (PROPOSED)", unapproved=True),
            chunk("hours", "We are open from Monday to Friday."),
        ]

    def search(self, sims, query="how do I get my money back", **kw):
        return Index(self.chunks, vectors=FakeVectors(sims) if sims is not None else None).search(query, **kw)

    def ids(self, hits):
        return [c["id"] for _, c in hits]

    def test_meaning_match_is_found_even_without_shared_words(self):
        hits = self.search([0.1, 0.8, 0.1, 0.1], query="reimbursement please")
        self.assertEqual(self.ids(hits), ["refund"])

    def test_drafts_are_hidden_from_semantic_results(self):
        hits = self.search([0.1, 0.6, 0.9, 0.1])
        self.assertNotIn("draft", self.ids(hits))
        self.assertIn("refund", self.ids(hits))

    def test_drafts_visible_when_explicitly_allowed(self):
        self.assertIn("draft", self.ids(self.search([0.1, 0.6, 0.9, 0.1], include_drafts=True)))

    def test_below_cutoff_adds_nothing(self):
        self.assertEqual(self.search([0.2, 0.3, 0.1, 0.34], query="xqzv plorb wumble"), [])

    def test_keyword_and_meaning_agreeing_rank_first(self):
        hits = self.search([0.1, 0.7, 0.1, 0.4], query="money returned parcel")
        self.assertEqual(self.ids(hits)[0], "refund")

    def test_no_vectors_means_plain_keyword_search(self):
        plain = Index(self.chunks).search("shipping price germany")
        self.assertEqual(self.ids(self.search(None, query="shipping price germany")), self.ids(plain))

    def test_failed_vector_search_falls_back_to_keywords(self):
        hits = self.search(None, query="shipping price germany")
        self.assertEqual(self.ids(hits)[0], "price")
        self.assertEqual(self.ids(Index(self.chunks, vectors=FakeVectors(None)).search("shipping price germany"))[0], "price")

    def test_result_count_is_limited(self):
        self.assertLessEqual(len(self.search([0.9, 0.9, 0.9, 0.9], k=2)), 2)


@unittest.skipIf(np is None, "numpy not installed")
class VectorsClassTests(unittest.TestCase):
    def test_best_similarity_per_chunk_and_failure_switches_it_off(self):
        class Emb:
            def embed(self, texts):
                return np.array([[1.0, 0.0]], dtype=np.float32)
        matrix = np.array([[1, 0], [0, 1], [0.6, 0.8]], dtype=np.float32)
        v = embed.Vectors(matrix, np.array([0, 1, 1]), 2, Emb())
        s = v.scores("q")
        self.assertAlmostEqual(float(s[0]), 1.0)
        self.assertAlmostEqual(float(s[1]), 0.6, places=5)  # the better of chunk 1's two windows

        class Broken:
            def embed(self, texts):
                raise RuntimeError("boom")
        b = embed.Vectors(matrix, np.array([0, 1, 1]), 2, Broken())
        self.assertIsNone(b.scores("q"))
        self.assertIsNone(b.scores("q"))  # stays off, and never raises into the chat

    def test_long_questions_are_cut(self):
        seen = []

        class Emb:
            def embed(self, texts):
                seen.append(texts[0])
                return np.array([[1.0, 0.0]], dtype=np.float32)
        embed.Vectors(np.eye(2, dtype=np.float32), np.array([0, 1]), 2, Emb()).scores("x" * 100_000)
        self.assertEqual(len(seen[0]), embed.MAX_QUERY_CHARS)


class LoadSwitchTests(unittest.TestCase):
    def test_can_be_switched_off(self):
        os.environ["EMBEDDINGS"] = "off"
        try:
            self.assertIsNone(embed.load_vectors([chunk("a", "alpha")], quiet=True))
        finally:
            os.environ.pop("EMBEDDINGS", None)

    def test_missing_index_files_mean_keyword_search_not_a_crash(self):
        orig = (embed.VEC_PATH, embed.META_PATH)
        embed.VEC_PATH = embed.META_PATH = Path(tempfile.gettempdir()) / "does-not-exist-xyz"
        try:
            self.assertIsNone(embed.load_vectors([chunk("a", "alpha")], quiet=True))
        finally:
            embed.VEC_PATH, embed.META_PATH = orig


def _model_ready():
    try:
        import fastembed  # noqa: F401
        embed.verify_model()
        embed.check_files(json.loads((embed.ROOT / "index" / "chunks.json").read_text(encoding="utf-8")))
        return True
    except Exception:
        return False


@unittest.skipUnless(_model_ready(), "model not downloaded or vector index not built")
class RealModelTests(unittest.TestCase):
    """Uses the real downloaded model, fully offline."""

    @classmethod
    def setUpClass(cls):
        cls.index = Index.load()

    def test_vectors_are_active(self):
        self.assertIsNotNone(self.index.vectors)

    def test_german_question_finds_the_english_page(self):
        files = [c["file"] for _, c in self.index.search("Wie lange dauert eine Webseite", k=3)]
        self.assertIn("website-design/process-cost-timeline.md", files)

    def test_paraphrase_finds_returns_page(self):
        files = [c["file"] for _, c in self.index.search("how do I get my money back", k=3)]
        self.assertIn("hair-store/ordering-shipping-returns.md", files)

    def test_off_topic_questions_get_nothing_extra_from_meaning_search(self):
        plain = Index(self.index.chunks)  # same chunks, keyword search only
        self.assertEqual(self.index.search("xqzv plorb wumble"), [])
        for q in ("write me a poem about autumn", "what's the weather tomorrow", "Wie wird das Wetter morgen"):
            self.assertEqual([c["id"] for _, c in self.index.search(q)], [c["id"] for _, c in plain.search(q)], q)

    def test_no_internet_is_used(self):
        self.assertEqual(os.environ.get("HF_HUB_OFFLINE"), "1")


if __name__ == "__main__":
    unittest.main()
