"""Streaming tests: the marker filter, the model stream reader, the assistant, and the HTTP endpoint."""
import http.client
import json
import os
import random
import tempfile
import threading
import time
import unittest

from rag import assistant, claude, feedback, server, streaming
from rag.retrieve import Index
from tests.test_admin import Base
from tests.test_handoff import CONSENT_ASKED, GOOD


def feed_all(pieces):
    f = streaming.MarkerFilter()
    out = [f.feed(p) for p in pieces]
    out.append(f.flush())
    return out


class MarkerFilterTests(unittest.TestCase):
    def test_a_marker_cut_at_every_possible_place_never_reaches_the_customer(self):
        text = "Pick a time below.\n[[book]]"
        for cut in range(len(text) + 1):
            pieces = feed_all([text[:cut], text[cut:]])
            for piece in pieces:
                self.assertNotIn("[[", piece, f"cut at {cut}: {piece!r}")
                self.assertNotIn("[", piece, f"cut at {cut}: {piece!r}")  # not even a lone '[' of it
            self.assertEqual("".join(pieces), "Pick a time below.\n", f"cut at {cut}")

    def test_marker_arriving_one_character_at_a_time(self):
        for text in ("Sorry.\n[[gap]]", "Sure [[ BOOK ]] ok", "[[Book]]x"):
            pieces = feed_all(list(text))
            self.assertFalse(any("[" in p and "]" not in p and "[[" in p for p in pieces))
            joined = "".join(pieces)
            self.assertIsNone(streaming.FULL.search(joined))
            self.assertNotIn("[[", joined)

    def test_ordinary_brackets_are_shown_in_full(self):
        for text in ("see [1] and [note] for details", "price [incl. VAT]", "a [ b ] c", "[x]"):
            self.assertEqual("".join(feed_all([text])), text)
            self.assertEqual("".join(feed_all(list(text))), text)

    def test_a_half_marker_at_the_very_end_is_released_not_swallowed(self):
        self.assertEqual("".join(feed_all(["Hello [[ga"])), "Hello [[ga")
        self.assertEqual("".join(feed_all(["Hello ["])), "Hello [")

    def test_both_markers_and_reset(self):
        self.assertEqual("".join(feed_all(["A.\n[[gap]]\n[[book]]"])), "A.\n\n")
        f = streaming.MarkerFilter()
        f.feed("text [[bo")
        f.reset()
        self.assertEqual(f.flush(), "")

    def test_text_without_brackets_is_never_changed_or_delayed_beyond_one_piece(self):
        rnd = random.Random(7)
        for _ in range(300):
            text = "".join(rnd.choice("abc def\n.,€ü") for _ in range(rnd.randint(0, 60)))
            cuts = sorted(rnd.sample(range(len(text) + 1), min(3, len(text) + 1)))
            pieces = [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]
            f = streaming.MarkerFilter()
            for p in pieces:
                self.assertEqual(f.feed(p), p)
            self.assertEqual(f.flush(), "")

    def test_fuzz_no_complete_marker_and_no_marker_prefix_ever_leaks_mid_stream(self):
        rnd = random.Random(11)
        atoms = ["a", " ", "\n", "[", "]", "b", "o", "k", "g", "p", "[[book]]", "[[gap]]", "[[", "]]", "bo", "ga"]
        for _ in range(3000):
            text = "".join(rnd.choice(atoms) for _ in range(rnd.randint(1, 14)))
            cuts = sorted(rnd.sample(range(len(text) + 1), min(rnd.randint(1, 4), len(text) + 1)))
            pieces = [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]
            out = "".join(feed_all(pieces))
            self.assertIsNone(streaming.FULL.search(out), (text, pieces, out))  # no complete marker survives
            # If a half marker had leaked early, its second half would later join it into a full marker (caught above)
            # or the result would depend on where the stream was cut. It must not (spacing around markers aside).
            whole = "".join(feed_all([text]))
            squash = lambda s: "".join(s.split())
            self.assertEqual(squash(out), squash(whole), (text, pieces))


def sse(*events, lines=()):
    out = []
    for ev in events:
        out.append(f"event: {ev['type']}")
        out.append("data: " + json.dumps(ev))
        out.append("")
    out.extend(lines)
    return out


class FakeResponse:
    def __init__(self, lines):
        self.lines = [(l + "\n").encode("utf-8") for l in lines]
        self.closed = False

    def __iter__(self):
        return iter(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.closed = True
        return False


class StreamReaderTests(unittest.TestCase):
    def setUp(self):
        self.orig = claude.urllib.request.urlopen
        os.environ["ANTHROPIC_API_KEY"] = "test"
        self.sent = []

    def tearDown(self):
        claude.urllib.request.urlopen = self.orig

    def use(self, lines):
        resp = FakeResponse(lines)

        def fake(req, timeout=None):
            self.sent.append(json.loads(req.data))
            return resp
        claude.urllib.request.urlopen = fake
        return resp

    def test_text_is_passed_on_piece_by_piece_and_collected(self):
        self.use(sse(
            {"type": "message_start", "message": {}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "lo"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
            {"type": "message_stop"}, lines=[": ping"]))
        pieces = []
        data = claude.chat_stream("m", [{"role": "user", "content": "hi"}], on_text=pieces.append)
        self.assertEqual(pieces, ["Hel", "lo"])
        self.assertEqual(data, {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Hello"}]})
        self.assertTrue(self.sent[0]["stream"])
        self.assertEqual(claude.text_of(data), "Hello")

    def test_tool_call_is_rebuilt_from_json_pieces(self):
        self.use(sse(
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "One moment."}},
            {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "t1", "name": "escalate_to_human", "input": {}}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"name": "An'}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": 'na", "consent": true}'}},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"}}))
        data = claude.chat_stream("m", [], on_text=lambda p: None)
        self.assertEqual(data["stop_reason"], "tool_use")
        self.assertEqual(data["content"][1], {"type": "tool_use", "id": "t1", "name": "escalate_to_human", "input": {"name": "Anna", "consent": True}})
        self.assertNotIn("_json", json.dumps(data))

    def test_broken_tool_json_becomes_empty_input_not_a_crash(self):
        self.use(sse(
            {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "t", "name": "x", "input": {}}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"a": '}},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"}}))
        self.assertEqual(claude.chat_stream("m", [])["content"][0]["input"], {})

    def test_error_event_and_garbage_lines(self):
        self.use(["data: not json", "data: ", "random line"] + sse({"type": "error", "error": {"type": "overloaded_error", "message": "secret detail"}}))
        with self.assertRaises(claude.ClaudeError) as cm:
            claude.chat_stream("m", [])
        self.assertNotIn("secret detail", str(cm.exception))

    def test_stops_reading_and_closes_the_connection_when_the_listener_is_gone(self):
        resp = self.use(sse(
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            *[{"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "x"}}] * 50))
        seen = []

        def gone(piece):
            seen.append(piece)
            if len(seen) == 3:
                raise server.ClientGone()
        with self.assertRaises(server.ClientGone):
            claude.chat_stream("m", [], on_text=gone)
        self.assertEqual(len(seen), 3)  # it did not read on
        self.assertTrue(resp.closed)

    def test_a_flood_of_content_blocks_is_refused(self):
        self.use(sse(*[{"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}} for i in range(100)]))
        with self.assertRaises(claude.ClaudeError):
            claude.chat_stream("m", [])


class AssistantStreamTests(unittest.TestCase):
    def chunk(i, text):
        return {"id": i, "file": f"{i}.md", "heading": "Test", "unapproved": False, "placeholders": 0, "text": text}
    HOURS = chunk("hours", "We are open Monday to Friday from 8 to 18 and Saturday from 10 to 14")
    OTHERS = [chunk("ship", "Shipping inside Germany takes three days with tracking"),
              chunk("pay", "You can pay by card, bank transfer or invoice for business customers")]

    def setUp(self):
        self.orig = (assistant.claude.chat, assistant.claude.chat_stream, assistant.claude.create)
        self.scripts = []
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HANDOFF_DIR"] = self.tmp.name
        os.environ["ANTHROPIC_API_KEY"] = "test"
        assistant.claude.create = lambda model, max_tokens, messages: messages[0]["content"].split("Latest message: ")[-1]

        def fake_stream(on_text=None, **options):
            script = self.scripts.pop(0)
            for piece in script["pieces"]:
                on_text(piece)
            content = [{"type": "text", "text": "".join(script["pieces"])}] + script.get("tools", [])
            return {"stop_reason": script.get("stop", "end_turn"), "content": content}
        assistant.claude.chat_stream = fake_stream

    def tearDown(self):
        assistant.claude.chat, assistant.claude.chat_stream, assistant.claude.create = self.orig
        os.environ.pop("HANDOFF_DIR", None)
        self.tmp.cleanup()

    def run_stream(self, question, history=None, **kw):
        events = []
        bot = assistant.Assistant(index=Index([self.HOURS] + self.OTHERS), **kw)
        if history:
            bot.history = list(history)
        answer, _, _ = bot.ask(question, on_event=lambda kind, payload: events.append((kind, payload)))
        return bot, answer, events

    def shown(self, events):
        return "".join(p for k, p in events if k == "text")

    def test_markers_split_across_pieces_never_reach_the_customer_and_still_work(self):
        self.scripts.append({"pieces": ["Pick a time below.", "\n[[bo", "ok]]", "\n[[g", "ap]]"]})
        bot, answer, events = self.run_stream("When are you open on Saturday?")
        self.assertNotIn("[", self.shown(events))
        self.assertEqual(answer, "Pick a time below.")
        self.assertEqual(self.shown(events).strip(), answer)
        self.assertEqual(bot.gap, "unanswered")  # the markers did their job without being shown

    def test_streamed_text_matches_the_final_answer(self):
        self.scripts.append({"pieces": ["We are open ", "Monday to Friday ", "from 8 to 18."]})
        bot, answer, events = self.run_stream("When are you open on Saturday?")
        self.assertEqual(self.shown(events), answer)
        self.assertEqual(bot.history[-1], {"role": "assistant", "content": answer})
        self.assertEqual(bot.gap, "")

    def test_text_before_a_tool_call_is_withdrawn_and_the_handoff_still_happens(self):
        tool = {"type": "tool_use", "id": "t1", "name": "escalate_to_human", "input": GOOD}
        self.scripts.append({"pieces": ["One moment, ", "passing this on."], "stop": "tool_use", "tools": [tool]})
        self.scripts.append({"pieces": ["Done. Your reference is below."]})
        bot, answer, events = self.run_stream("Yes, please do", history=CONSENT_ASKED)  # asked, and the customer said yes
        kinds = [k for k, _ in events]
        self.assertEqual(kinds.count("reset"), 1)
        after_reset = "".join(p for k, p in events[kinds.index("reset"):] if k == "text")
        self.assertEqual(after_reset, answer)
        self.assertEqual(answer, "Done. Your reference is below.")
        self.assertTrue((os.path.join(self.tmp.name, "handoffs.jsonl")) and os.path.exists(os.path.join(self.tmp.name, "handoffs.jsonl")))

    def test_listener_leaving_stops_the_answer_and_keeps_history_clean(self):
        self.scripts.append({"pieces": ["a", "b", "c", "d"]})
        bot = assistant.Assistant(index=Index([self.HOURS] + self.OTHERS))

        def gone(kind, payload):
            raise server.ClientGone()
        with self.assertRaises(server.ClientGone):
            bot.ask("When are you open on Saturday?", on_event=gone)
        self.assertEqual(bot.history, [])

    def test_without_on_event_the_normal_path_is_used(self):
        assistant.claude.chat = lambda **k: {"stop_reason": "end_turn", "content": [{"type": "text", "text": "plain answer"}]}
        bot = assistant.Assistant(index=Index([self.HOURS] + self.OTHERS))
        self.assertEqual(bot.ask("When are you open on Saturday?")[0], "plain answer")
        self.assertEqual(self.scripts, [])


class SlowBot:
    """Streams many pieces slowly, so a test can hang up in the middle."""
    aborted = threading.Event()
    started = threading.Event()

    def __init__(self, *a, **k):
        self.history = []

    def ask(self, text, note="", on_event=None):
        SlowBot.started.set()
        try:
            for i in range(300):
                on_event("text", f"piece{i} ")
                time.sleep(0.01)
        except BaseException:
            SlowBot.aborted.set()
            raise
        return "done", [], text


class StreamHttpTests(Base):
    def post(self, path="/api/chat/stream", data=None, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        return self.req("POST", path, json.dumps(data if data is not None else {"message": "hello world"}), h)

    @staticmethod
    def events(body):
        out = []
        for block in body.split("\n\n"):
            if block.startswith("data: "):
                out.append(json.loads(block[6:]))
        return out

    def test_answer_arrives_in_pieces_and_ends_with_the_same_result_as_the_normal_endpoint(self):
        status, h, body = self.post(data={"message": "hello streaming world"})
        self.assertEqual(status, 200)
        self.assertTrue(h["content-type"][0].startswith("text/event-stream"))
        self.assertEqual(h["cache-control"], ["no-store"])
        self.assertEqual(h["x-accel-buffering"], ["no"])
        ev = self.events(body)
        self.assertIn("session_id", ev[0])
        pieces = [e["t"] for e in ev if "t" in e]
        self.assertGreater(len(pieces), 3)
        done = ev[-1]["done"]
        self.assertEqual("".join(pieces), done["reply"])
        self.assertEqual(done["reply"], "echo: hello streaming world")
        self.assertEqual(done["fid"], feedback.answer_id(done["reply"]))
        self.assertEqual(set(done), {"session_id", "reply", "fid", "book", "next", "sources", "unsure"})
        self.assertEqual(done["session_id"], ev[0]["session_id"])

    def test_the_session_is_kept_across_streamed_and_normal_requests(self):
        sid = self.events(self.post()[2])[0]["session_id"]
        again = self.events(self.post(data={"message": "again", "session_id": sid})[2])
        self.assertEqual(again[0]["session_id"], sid)

    def test_booking_flag_in_the_final_event(self):
        original = self.app.booking
        self.app.booking = "https://calendly.com/faiyke/intro"
        try:
            done = self.events(self.post(data={"message": "call please [[book]]"})[2])[-1]["done"]
        finally:
            self.app.booking = original
        self.assertTrue(done["book"])
        self.assertNotIn("[[", done["reply"])

    def test_same_checks_as_the_normal_endpoint(self):
        self.assertEqual(self.post(data={"message": ""})[0], 400)
        self.assertEqual(self.post(data={"message": "x" * 1001})[0], 400)
        self.assertEqual(self.req("POST", "/api/chat/stream", "not json", {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.post(headers={"Origin": "https://evil.example"})[0], 403)
        status, h, _ = self.post(headers={"Origin": "https://faiyke.example"})
        self.assertEqual((status, h["access-control-allow-origin"]), (200, ["https://faiyke.example"]))

    def test_errors_come_as_plain_json_not_as_a_stream(self):
        status, h, body = self.post(data={"message": ""})
        self.assertTrue(h["content-type"][0].startswith("application/json"))
        self.assertIn("error", json.loads(body))

    def test_rate_limit_and_daily_cap_apply(self):
        orig = (self.app.limiter, self.app.cap)
        try:
            self.app.limiter = server.RateLimiter(1)
            self.assertEqual(self.post()[0], 200)
            self.assertEqual(self.post()[0], 429)
            self.app.limiter = orig[0]
            self.app.cap = server.DailyCap(0)
            self.assertEqual(self.post()[0], 503)
        finally:
            self.app.limiter, self.app.cap = orig

    def test_too_many_streams_at_once_get_busy_and_slots_are_given_back(self):
        orig = self.app.streams
        try:
            self.app.streams = threading.BoundedSemaphore(1)
            self.assertTrue(self.app.streams.acquire(blocking=False))  # someone else holds the only slot
            status, _, body = self.post()
            self.assertEqual(status, 503)
            self.assertIn("busy", json.loads(body)["error"])
            self.app.streams.release()
            self.assertEqual(self.post()[0], 200)  # a finished stream gives its slot back
            self.assertEqual(self.post()[0], 200)
        finally:
            self.app.streams = orig

    def test_leaving_midway_stops_the_model_and_frees_the_slot(self):
        orig_bot, orig_streams = server.Assistant, self.app.streams
        server.Assistant = SlowBot
        self.app.streams = threading.BoundedSemaphore(2)
        self.app.sessions.items.clear()
        SlowBot.aborted.clear(); SlowBot.started.clear()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            conn.request("POST", "/api/chat/stream", json.dumps({"message": "hello slowly"}), {"Content-Type": "application/json"})
            resp = conn.getresponse()
            resp.fp.readline()  # the first event arrived
            self.assertTrue(SlowBot.started.wait(3))
            resp.close(); conn.close()  # the customer closes the page
            self.assertTrue(SlowBot.aborted.wait(5), "the answer kept being generated for nobody")
            deadline = time.time() + 5
            while self.app.streams._value < 2 and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual(self.app.streams._value, 2)
        finally:
            server.Assistant, self.app.streams = orig_bot, orig_streams
            self.app.sessions.items.clear()

    def test_slow_clients_are_cut_off_after_a_timeout(self):
        self.assertEqual(server.make_handler(self.app).timeout, 30)

    def test_normal_endpoint_is_unchanged(self):
        status, _, body = self.req("POST", "/api/chat", json.dumps({"message": "plain hello"}), {"Content-Type": "application/json"})
        d = json.loads(body)
        self.assertEqual((status, d["reply"], set(d)), (200, "echo: plain hello", {"session_id", "reply", "fid", "book", "next", "sources", "unsure"}))


if __name__ == "__main__":
    unittest.main()
