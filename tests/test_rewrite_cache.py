"""The query rewrite is cached per index, so repeated questions cost one API call, not one per visitor."""
import os
import unittest

from rag import assistant
from rag.retrieve import Index


def make_index():
    chunk = {"id": "a", "file": "x.md", "heading": "H", "text": "price", "unapproved": False, "placeholders": False}
    return Index([chunk])


class RewriteCacheTests(unittest.TestCase):
    def setUp(self):
        self.orig = assistant.claude.create
        self.calls = []

        def fake(model, max_tokens, messages):
            self.calls.append(1)
            return "price query"
        assistant.claude.create = fake

    def tearDown(self):
        assistant.claude.create = self.orig

    def test_same_question_calls_the_model_once_across_visitors(self):
        index = make_index()
        a, b = assistant.Assistant(index=index), assistant.Assistant(index=index)
        self.assertEqual(a.rewrite("how much?"), "price query")
        self.assertEqual(b.rewrite("how much?"), "price query")
        self.assertEqual(len(self.calls), 1)

    def test_different_context_is_not_shared(self):
        index = make_index()
        a, b = assistant.Assistant(index=index), assistant.Assistant(index=index)
        b.history = [{"role": "user", "content": "hair"}, {"role": "assistant", "content": "ok"}]
        a.rewrite("and the price?")
        b.rewrite("and the price?")
        self.assertEqual(len(self.calls), 2)

    def test_failures_are_not_cached(self):
        def boom(model, max_tokens, messages):
            raise RuntimeError("down")
        assistant.claude.create = boom
        index = make_index()
        bot = assistant.Assistant(index=index)
        self.assertEqual(bot.rewrite("hi"), "hi")  # falls back to the raw question
        self.assertEqual(index.rewrite_cache, {})

    def test_cache_is_bounded(self):
        index = make_index()
        bot = assistant.Assistant(index=index)
        for i in range(assistant.REWRITE_CACHE_MAX + 20):
            bot.rewrite(f"question {i}")
        self.assertLessEqual(len(index.rewrite_cache), assistant.REWRITE_CACHE_MAX)


class RewriteModeTests(unittest.TestCase):
    def setUp(self):
        self.orig_create, self.orig_chat = assistant.claude.create, assistant.claude.chat
        self.rewrites = []
        assistant.claude.create = lambda model, max_tokens, messages: (self.rewrites.append(1), "q")[1]
        assistant.claude.chat = lambda **k: {"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}

    def tearDown(self):
        assistant.claude.create, assistant.claude.chat = self.orig_create, self.orig_chat
        os.environ.pop("RAG_REWRITE", None)

    def test_default_rewrites_every_message(self):
        bot = assistant.Assistant(index=make_index())
        bot.ask("first")
        bot.ask("second")
        self.assertEqual(len(self.rewrites), 2)

    def test_auto_skips_only_the_first_message(self):
        os.environ["RAG_REWRITE"] = "auto"
        bot = assistant.Assistant(index=make_index())
        bot.ask("first")
        self.assertEqual(len(self.rewrites), 0)
        bot.ask("and that one?")
        self.assertEqual(len(self.rewrites), 1)


if __name__ == "__main__":
    unittest.main()
