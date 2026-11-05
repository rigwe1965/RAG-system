"""Knowledge gaps: questions the assistant could not answer, so you can see what to add to the knowledge base.

Saved to gaps/gaps.jsonl (override the folder with GAPS_DIR). Shown on the admin dashboard (rag/admin.py).
Switch off completely with LOG_GAPS=off.

Three kinds:
    no_match    nothing in the knowledge base matched the question
    pending     the only good answer is still a hidden draft (PROPOSED)
    unanswered  the assistant said it does not have that detail (it adds the marker [[gap]], removed before the
                customer sees the answer)

Privacy rules (each has a test): emails and phone numbers are removed from the question, it is cut to
300 characters, only a hash of the chat id is stored (so a customer's "delete my chat" also deletes these),
old rows are deleted automatically (RETENTION_GAPS_DAYS, default 60), and the number of rows per day and the
file size are capped.
"""
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .feedback import scrub

ROOT = Path(__file__).resolve().parent.parent
KINDS = {"no_match", "pending", "unanswered"}
MAX_QUESTION = 300
MAX_FILE_BYTES = 3_000_000
MIN_QUESTION_CHARS = 12  # "hi", "thanks" and the like are not knowledge gaps
MARKER = re.compile(r"[ \t]*\[\[\s*gap\s*\]\][ \t]*", re.IGNORECASE)


def strip_marker(answer):
    """Remove the [[gap]] marker from an answer. Returns (text, was_marked)."""
    if not MARKER.search(answer):
        return answer, False
    text = MARKER.sub(" ", answer)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip(), True


def key_hash(key):
    return hashlib.sha256(("gap:" + key).encode("utf-8")).hexdigest()[:12]


def enabled():
    return os.environ.get("LOG_GAPS", "on").strip().lower() not in ("off", "0", "false", "no")


class GapStore:
    def __init__(self, folder=None, daily_cap=None):
        self.folder = Path(folder or os.environ.get("GAPS_DIR", ROOT / "gaps"))
        self.daily_cap = daily_cap if daily_cap is not None else int(os.environ.get("GAPS_DAILY_CAP", "500"))
        self.day, self.count, self.lock = None, 0, threading.Lock()

    @property
    def path(self):
        return self.folder / "gaps.jsonl"

    def record(self, kind, question, key, sources=(), today=None):
        """Save one gap. Returns False when it was skipped (too short, bad kind, or a cap was reached)."""
        question = scrub(question, MAX_QUESTION)
        if kind not in KINDS or len(question) < MIN_QUESTION_CHARS:
            return False
        today = today or time.strftime("%Y-%m-%d")
        row = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "question": question,
            "sources": [str(s)[:120] for s in list(sources)[:5]],
            "session": key_hash(key) if key else None,
        }
        with self.lock:
            if today != self.day:
                self.day, self.count = today, 0
            if self.count >= self.daily_cap:
                return False
            self.folder.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size >= MAX_FILE_BYTES:
                return False
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.count += 1
        return True

    def rewrite(self, keep):
        from .privacy import rewrite_jsonl  # imported here: privacy.py imports this module
        return rewrite_jsonl(self.path, keep, self.lock)

    def forget(self, key):
        """Delete every gap recorded from this chat. Returns the number removed."""
        wanted = key_hash(key)
        return self.rewrite(lambda row: row.get("session") != wanted)
