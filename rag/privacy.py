"""Privacy tools (GDPR): automatic deletion of old records, and erasure on request.

    python -m rag.privacy status                              # what is stored, and how old
    python -m rag.privacy purge                               # delete records older than the retention periods
    python -m rag.privacy erase --contact anna@example.com    # delete a person's hand-off records and open chats (email or phone)
    python -m rag.privacy erase --reference FAI-20261105-001  # ... or one hand-off by its reference

Settings (days; 0 switches that deletion off):
    RETENTION_HANDOFF_DAYS   hand-off records            (default 180)
    RETENTION_FEEDBACK_DAYS  thumbs up/down records      (default 90)
    RETENTION_LOGS_DAYS      terminal chat log (--log)   (default 30)
    RETENTION_GAPS_DAYS      unanswered questions        (default 60)
    PRIVACY_URL              https link to your privacy policy, shown in the chat

The server runs the purge when it starts and then once a day.

What this cannot do: a hand-off is also emailed to you. Copies in your mailbox, and anything your
email provider keeps, must be deleted by you. `erase` tells you which references to look for.
Customers can delete their own chat data from the chat page (POST /api/forget): the server's copy of the
conversation, their feedback records and their saved chats in the browser.
"""
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import booking, feedback, gaps, handoff, sessionstore

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DAYS = {"RETENTION_HANDOFF_DAYS": 180, "RETENTION_FEEDBACK_DAYS": 90, "RETENTION_LOGS_DAYS": 30,
                "RETENTION_GAPS_DAYS": 60}
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
LOG_PATH = ROOT / "logs" / "conversations.jsonl"  # written by `python -m rag.assistant --log`
_file_lock = threading.Lock()  # for files nobody else writes to at the same time


def retention_days(name):
    """Days to keep, 0 = keep forever (deletion off). Bad values fall back to the default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return DEFAULT_DAYS[name]
    try:
        n = int(raw)
    except ValueError:
        return DEFAULT_DAYS[name]
    return n if n >= 0 else DEFAULT_DAYS[name]


def privacy_url():
    """The configured privacy-policy link if it passes the same checks as the booking link, else None."""
    raw = os.environ.get("PRIVACY_URL", "").strip()
    if not raw:
        return None
    try:
        return booking.parse(raw)
    except ValueError as e:
        print(f"[privacy] PRIVACY_URL ignored: {e}", file=sys.stderr)
        return None


def _parse_time(value):
    try:
        t = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def rewrite_jsonl(path, keep, lock):
    """Keep only the lines for which keep(row) is true. Lines that cannot be read are kept, never destroyed.
    Writes a new file and swaps it in, so a crash cannot leave a half-written file. Returns the number removed."""
    path = Path(path)
    with lock:
        if not path.exists():
            return 0
        kept, removed = [], 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                kept.append(line)
                continue
            if isinstance(row, dict) and not keep(row):
                removed += 1
            else:
                kept.append(line)
        if removed:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text("".join(k + "\n" for k in kept), encoding="utf-8")
            os.replace(tmp, path)
        return removed


def _older_than(days, now):
    cutoff = now - timedelta(days=days)

    def old(row):
        t = _parse_time(row.get("time"))
        return t is not None and t < cutoff  # a record without a readable time is kept
    return old


def _sync_emailed_marks():
    """Forget 'emailed' marks of hand-offs that no longer exist, so the list does not grow forever."""
    marks = handoff._dir() / "emailed.txt"
    if not marks.exists():
        return
    alive = {r["reference"] for r in handoff.read_records()}
    kept = [r for r in marks.read_text(encoding="utf-8").split() if r in alive]
    marks.write_text("".join(r + "\n" for r in kept), encoding="utf-8")


def purge(now=None):
    """Delete records older than their retention period. Returns {name: number removed}."""
    now = now or datetime.now(timezone.utc)
    out = {"handoffs": 0, "feedback": 0, "logs": 0, "gaps": 0, "sessions": 0}
    if sessionstore.default_path().exists():  # open chats expire after 30 minutes; this also clears a leftover file
        store = sessionstore.SessionStore(sessionstore.default_path())
        out["sessions"] = store.purge(now.timestamp())
        store.close()
    d = retention_days("RETENTION_HANDOFF_DAYS")
    if d:
        out["handoffs"] = rewrite_jsonl(handoff._dir() / "handoffs.jsonl", lambda r: not _older_than(d, now)(r), handoff._lock)
        if out["handoffs"]:
            _sync_emailed_marks()
    d = retention_days("RETENTION_FEEDBACK_DAYS")
    if d:
        out["feedback"] = feedback.FeedbackStore().rewrite(lambda r: not _older_than(d, now)(r))
    d = retention_days("RETENTION_GAPS_DAYS")
    if d:
        out["gaps"] = gaps.GapStore().rewrite(lambda r: not _older_than(d, now)(r))
    d = retention_days("RETENTION_LOGS_DAYS")
    if d:
        out["logs"] = rewrite_jsonl(LOG_PATH, lambda r: not _older_than(d, now)(r), _file_lock)
    return out


def normalise_contact(text):
    """Email: lower case. Phone: digits only. So '+49 176 41565516' equals '0049176 41565516'-style variants."""
    text = (text or "").strip()
    if "@" in text:
        m = EMAIL.search(text)
        return m.group(0).lower() if m else text.lower()
    digits = re.sub(r"\D", "", text)
    return digits[2:] if digits.startswith("00") else digits


def erase_handoffs(reference=None, contact=None):
    """Delete hand-off records by reference or by the customer's contact. Returns the removed references."""
    if not reference and not contact:
        raise ValueError("give a reference or a contact")
    want = normalise_contact(contact) if contact else None
    removed = []

    def keep(row):
        hit = (reference and row.get("reference") == reference) or \
              (want and normalise_contact(row.get("contact", "")) == want and want != "")
        if hit:
            removed.append(row.get("reference", "?"))
        return not hit
    rewrite_jsonl(handoff._dir() / "handoffs.jsonl", keep, handoff._lock)
    if removed:
        _sync_emailed_marks()
    return removed


def erase_sessions(contact):
    """Delete saved open chats that mention this email/phone, and the WhatsApp chat of that number.
    Returns the number removed."""
    path = sessionstore.default_path()
    if not contact or not path.exists():
        return 0
    want = normalise_contact(contact)
    needles = {contact.strip(), want}
    store = sessionstore.SessionStore(path)
    try:
        return store.erase_mentions([n for n in needles if len(n) >= 5], whatsapp_digits=None if "@" in contact else want)
    finally:
        store.close()


# ---------- daily background purge ----------

def start_background(interval_hours=24):
    """Purge now, then once a day, in a background thread. Never raises into the server."""
    def loop():
        while True:
            try:
                out = purge()
                if any(out.values()):
                    print(f"[privacy] deleted old records: {out}", file=sys.stderr)
            except Exception as e:
                print(f"[privacy] purge failed: {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(interval_hours * 3600)
    t = threading.Thread(target=loop, daemon=True, name="privacy-purge")
    t.start()
    return t


# ---------- command line ----------

def _age(path, now):
    times = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                t = _parse_time(json.loads(line).get("time"))
            except (ValueError, AttributeError):
                continue
            if t:
                times.append(t)
    if not times:
        return "0 records"
    return f"{len(times)} records, oldest {(now - min(times)).days} days"


def _cli(argv):
    from . import env
    env.load()
    now = datetime.now(timezone.utc)
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        for label, path, name in (
            ("Hand-offs", handoff._dir() / "handoffs.jsonl", "RETENTION_HANDOFF_DAYS"),
            ("Feedback", feedback.FeedbackStore().path, "RETENTION_FEEDBACK_DAYS"),
            ("Unanswered Qs", gaps.GapStore().path, "RETENTION_GAPS_DAYS"),
            ("Chat log (--log)", LOG_PATH, "RETENTION_LOGS_DAYS"),
        ):
            days = retention_days(name)
            print(f"{label:18} {_age(path, now):34} deleted after: {days} days" if days else
                  f"{label:18} {_age(path, now):34} automatic deletion OFF")
        if sessionstore.default_path().exists():
            store = sessionstore.SessionStore(sessionstore.default_path())
            count, oldest = store.stats()
            store.close()
            age = f", oldest {int(oldest // 60)} min" if oldest is not None else ""
            print(f"{'Open chats':18} {f'{count} chats{age}':34} deleted after: 30 minutes of silence")
        print("Privacy policy link:", privacy_url() or "not set (PRIVACY_URL)")
    elif cmd == "purge":
        print("Deleted:", purge())
    elif cmd == "erase":
        import argparse
        ap = argparse.ArgumentParser(prog="python -m rag.privacy erase")
        ap.add_argument("--contact")
        ap.add_argument("--reference")
        args = ap.parse_args(argv[1:])
        if not (args.contact or args.reference):
            sys.exit("Give --contact (email or phone) or --reference.")
        refs = erase_handoffs(args.reference, args.contact)
        chats = erase_sessions(args.contact) if args.contact else 0
        if chats:
            print(f"Deleted {chats} saved open chat(s) that mention this contact.")
        if refs:
            print("Deleted hand-off records:", ", ".join(refs))
            print("Also delete the emails about these references from your mailbox (subject contains the reference).")
        else:
            print("No matching hand-off records found.")
    else:
        sys.exit("Usage: python -m rag.privacy [status|purge|erase --contact X | erase --reference X]")


if __name__ == "__main__":
    _cli(sys.argv[1:])
