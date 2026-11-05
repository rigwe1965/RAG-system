"""Chats that survive a server restart.

Open chats normally live in memory (rag/server.py `Sessions`). This module keeps a small copy on disk
(sessions/sessions.db, SQLite, standard library only) so that after a restart or crash a customer can carry on
where they stopped, and so that a second server could pick the chat up.

What is stored, per chat: the recent messages (what the customer typed and the assistant answered, without the
retrieved knowledge-base passages), the rating-matching log (question text with emails/numbers removed), the chat
channel and the time of the last message. The chat key is stored only as a hash, so no phone number or browser
session id sits in the database.

Privacy rules (each has a test):
    - a chat is deleted 30 minutes after its last message (the same time the in-memory copy expires)
    - "delete my chat" deletes it (Sessions.forget -> SessionStore.delete)
    - `python -m rag.privacy erase --contact X` deletes chats that mention X (and a WhatsApp chat of that number)
    - the number of stored chats and the size of one chat are capped
    - a disk problem never breaks the chat: failures are reported on stderr and the chat carries on in memory

Switch off with PERSIST_SESSIONS=off. Change the folder with SESSIONS_DIR.
"""
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_ROWS = 2000            # stored chats
MAX_MESSAGES = 20          # recent messages kept per chat (the assistant itself only uses the last 6)
MAX_LOG = 30               # answers remembered per chat for ratings
MAX_ROW_BYTES = 200_000    # one chat's stored text


def enabled():
    return os.environ.get("PERSIST_SESSIONS", "on").strip().lower() not in ("off", "0", "false", "no")


def key_hash(key):
    return hashlib.sha256(("session:" + key).encode("utf-8")).hexdigest()


def default_path():
    return Path(os.environ.get("SESSIONS_DIR", ROOT / "sessions")) / "sessions.db"


def open_default():
    """The store for this server, or None when persistence is switched off or the database cannot be opened."""
    if not enabled():
        return None
    try:
        return SessionStore(default_path())
    except (sqlite3.Error, OSError) as e:
        print(f"[sessions] persistence disabled, cannot open {default_path()}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


class SessionStore:
    def __init__(self, path, ttl=30 * 60):
        self.path, self.ttl, self.lock = Path(path), ttl, threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=5)
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                " key_hash TEXT PRIMARY KEY, channel TEXT NOT NULL, seen REAL NOT NULL, data TEXT NOT NULL)")
            self.db.execute("CREATE INDEX IF NOT EXISTS sessions_seen ON sessions(seen)")
            self.db.commit()

    # --- every public method swallows disk errors: the chat must keep working from memory

    def _run(self, fn, default=None):
        try:
            with self.lock:
                result = fn(self.db)
                self.db.commit()
                return result
        except (sqlite3.Error, OSError, ValueError) as e:
            print(f"[sessions] {type(e).__name__}: {e}", file=sys.stderr)
            return default

    def save(self, key, channel, history, log, now=None):
        """Store the chat. `history` is a list of {"role", "content"}; `log` the rating-matching entries."""
        now = time.time() if now is None else now
        data = json.dumps({"history": list(history)[-MAX_MESSAGES:], "log": list(log)[-MAX_LOG:]}, ensure_ascii=False)
        if len(data.encode("utf-8")) > MAX_ROW_BYTES:
            data = json.dumps({"history": list(history)[-6:], "log": []}, ensure_ascii=False)

        def op(db):
            db.execute("INSERT OR REPLACE INTO sessions(key_hash, channel, seen, data) VALUES (?,?,?,?)",
                       (key_hash(key), channel, now, data))
            (n,) = db.execute("SELECT COUNT(*) FROM sessions").fetchone()
            if n > MAX_ROWS:
                db.execute("DELETE FROM sessions WHERE key_hash IN "
                           "(SELECT key_hash FROM sessions ORDER BY seen ASC LIMIT ?)", (n - MAX_ROWS,))
        self._run(op)

    def load(self, key, now=None):
        """Return {"channel", "seen", "history", "log"} for a chat that has not expired, else None."""
        now = time.time() if now is None else now

        def op(db):
            row = db.execute("SELECT channel, seen, data FROM sessions WHERE key_hash=?", (key_hash(key),)).fetchone()
            if not row:
                return None
            channel, seen, data = row
            if now - seen > self.ttl:
                db.execute("DELETE FROM sessions WHERE key_hash=?", (key_hash(key),))
                return None
            parsed = json.loads(data)
            history = [m for m in parsed.get("history", [])
                       if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]
            log = [e for e in parsed.get("log", []) if isinstance(e, dict) and "fid" in e]
            return {"channel": channel, "seen": seen, "history": history, "log": log}
        return self._run(op)

    def delete(self, key):
        return bool(self._run(lambda db: db.execute("DELETE FROM sessions WHERE key_hash=?", (key_hash(key),)).rowcount, 0))

    def purge(self, now=None):
        """Delete chats idle for longer than the time-to-live. Returns the number removed."""
        now = time.time() if now is None else now
        return self._run(lambda db: db.execute("DELETE FROM sessions WHERE seen < ?", (now - self.ttl,)).rowcount, 0) or 0

    def erase_mentions(self, needles, whatsapp_digits=None):
        """Delete chats whose text contains any of `needles` (case-insensitive), and the WhatsApp chat of a number.
        Returns the number removed."""
        needles = [n.lower() for n in needles if n]
        keys = {key_hash(f"wa:{whatsapp_digits}")} if whatsapp_digits else set()

        def op(db):
            doomed = set(keys)
            for kh, data in db.execute("SELECT key_hash, data FROM sessions"):
                low = data.lower()
                if any(n in low or json.dumps(n)[1:-1] in low for n in needles):
                    doomed.add(kh)
            removed = 0
            for kh in doomed:
                removed += db.execute("DELETE FROM sessions WHERE key_hash=?", (kh,)).rowcount
            return removed
        return self._run(op, 0) or 0

    def stats(self):
        """(count, age in seconds of the oldest chat or None)."""
        def op(db):
            n, oldest = db.execute("SELECT COUNT(*), MIN(seen) FROM sessions").fetchone()
            return n, oldest
        n, oldest = self._run(op, (0, None))
        return n, (max(0, time.time() - oldest) if oldest else None)

    def close(self):
        with self.lock:
            self.db.close()
