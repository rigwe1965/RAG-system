"""Thumbs up / down on assistant answers.

Ratings are appended to feedback/feedback.jsonl (override the folder with FEEDBACK_DIR).

    python -m rag.feedback            # summary and the latest thumbs-down

Privacy and safety rules (each has a test):
  * The browser sends only an answer ID, never text. The server looks up the question
    itself, so nobody can write made-up content into the log.
  * Only thumbs-down keeps the customer's question, and emails and phone numbers are
    removed from it (and from the optional comment) before saving.
  * The raw session id is never stored (it works like a password for the chat); only a hash.
  * Everything is length-limited, and the file and the number of entries per day are capped.
"""
import hashlib
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RATINGS = {"up", "down"}
MAX_BODY_BYTES = 2000
MAX_COMMENT = 300
MAX_QUESTION = 300
MAX_FILE_BYTES = 5_000_000
FID = re.compile(r"^[0-9a-f]{16}$")
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class FeedbackError(ValueError):
    pass


def answer_id(answer):
    """Short, stable ID for an answer. The server hands it out; the browser sends it back."""
    return hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16]


def session_hash(session_id):
    return hashlib.sha256(("feedback:" + session_id).encode("utf-8")).hexdigest()[:12]


def scrub(text, limit):
    """Remove contact details and control characters, collapse spaces, cut to `limit`."""
    text = EMAIL.sub("[email]", str(text or ""))
    text = PHONE.sub("[number]", text)
    text = CONTROL.sub(" ", text)
    return " ".join(text.split())[:limit]


def validate(data):
    """Return {"rating", "fid", "comment"} or raise FeedbackError. Never trusts the input."""
    if not isinstance(data, dict):
        raise FeedbackError("bad request")
    rating, fid, comment = data.get("rating"), data.get("fid"), data.get("comment", "")
    if rating not in RATINGS:
        raise FeedbackError("rating must be 'up' or 'down'")
    if not isinstance(fid, str) or not FID.match(fid):
        raise FeedbackError("bad answer id")
    if comment is None:
        comment = ""
    if not isinstance(comment, str):
        raise FeedbackError("comment must be text")
    if len(comment) > MAX_COMMENT:
        raise FeedbackError(f"comment too long (max {MAX_COMMENT} characters)")
    return {"rating": rating, "fid": fid, "comment": scrub(comment, MAX_COMMENT) if rating == "down" else ""}


class FeedbackStore:
    def __init__(self, folder=None, daily_cap=500):
        self.folder = Path(folder or os.environ.get("FEEDBACK_DIR", ROOT / "feedback"))
        self.daily_cap, self.day, self.count, self.lock = daily_cap, None, 0, threading.Lock()

    @property
    def path(self):
        return self.folder / "feedback.jsonl"

    def record(self, rating, fid, comment, session_id, context=None, today=None):
        """Append one entry. Returns False when a cap is reached (the caller still tells the user thanks)."""
        today = today or time.strftime("%Y-%m-%d")
        entry = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rating": rating,
            "fid": fid,
            "session": session_hash(session_id) if session_id else None,
            "comment": comment,
            "question": None,
            "sources": [],
        }
        if context:
            entry["sources"] = [str(s)[:120] for s in context.get("sources", [])][:8]
            if rating == "down":
                entry["question"] = scrub(context.get("question", ""), MAX_QUESTION)
        with self.lock:
            if today != self.day:
                self.day, self.count = today, 0
            if self.count >= self.daily_cap:
                return False
            self.folder.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size >= MAX_FILE_BYTES:
                return False
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self.count += 1
        return True

    def rewrite(self, keep):
        """Keep only rows for which keep(row) is true (retention and erasure). Returns the number removed."""
        from .privacy import rewrite_jsonl  # imported here: privacy.py itself imports this module
        return rewrite_jsonl(self.path, keep, self.lock)

    def forget(self, session_id):
        """Delete every rating given from this chat session. Returns the number removed."""
        wanted = session_hash(session_id)
        return self.rewrite(lambda row: row.get("session") != wanted)


def _summary(path):
    if not path.exists():
        return "No feedback yet."
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    latest = {}  # one vote per answer per session: the last one counts
    for r in rows:
        latest[(r.get("session"), r.get("fid"))] = r
    votes = list(latest.values())
    c = Counter(v["rating"] for v in votes)
    out = [f"{len(votes)} rated answers: {c['up']} up, {c['down']} down"]
    downs = [v for v in votes if v["rating"] == "down"]
    src = Counter(s for v in downs for s in v.get("sources", []))
    if src:
        out.append("\nKnowledge-base files behind thumbs-down answers:")
        out += [f"  {n}x {s}" for s, n in src.most_common(8)]
    if downs:
        out.append("\nLatest thumbs-down:")
        for v in downs[-10:]:
            out.append(f"  [{v['time'][:16]}] {v.get('question') or '(no question saved)'}")
            if v.get("comment"):
                out.append(f"      comment: {v['comment']}")
    return "\n".join(out)


if __name__ == "__main__":
    print(_summary(FeedbackStore().path))
    sys.exit(0)
