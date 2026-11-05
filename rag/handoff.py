"""Hand-off of a customer conversation to a human.

Every hand-off is saved to handoffs/handoffs.jsonl. If SMTP is configured it is
also emailed to the owner. Nothing is sent unless these environment variables are set:

    SMTP_HOST, SMTP_USER, SMTP_PASSWORD   (SMTP_PORT defaults to 587; Gmail needs an app password)
    HANDOFF_TO     recipient (default: info@faiyke.com)
    HANDOFF_FROM   sender (default: SMTP_USER)
    HANDOFF_DIR    where to store hand-offs (default: ./handoffs)
    HANDOFF_DAILY_CAP        hand-offs saved per day (default 200)
    HANDOFF_EMAIL_DAILY_CAP  hand-off emails sent per day (default 30; stops anyone flooding your inbox)

Commands (run from the project folder):
    python -m rag.handoff status    # is email set up? how many hand-offs were not emailed?
    python -m rag.handoff test      # send a test email to HANDOFF_TO
    python -m rag.handoff retry     # email hand-offs that were saved but not sent

Safety rules (each has a test): the mail server's certificate is always checked, customer
text is length-limited and stripped of control characters before it goes into an email,
the email headers never contain customer text, and error details stay in the server log,
never in the chat.
"""
import json
import os
import re
import smtplib
import ssl
import sys
import threading
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TO = "info@faiyke.com"
LINES = {"hair_store", "ai_agency", "website_design", "it_support", "crm", "general"}
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE = re.compile(r"\+?[\d][\d\s().-]{6,}")
SAFE_ADDRESS = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
LIMITS = {"name": 100, "company": 100, "contact": 120, "order_number": 40, "reason": 200, "summary": 600}
TRANSCRIPT_ITEM = 600
FIELDS = set(LIMITS) | {"business_line", "priority", "consent"}
_lock = threading.Lock()


class HandoffError(ValueError):
    pass


def _dir():
    d = Path(os.environ.get("HANDOFF_DIR", ROOT / "handoffs"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clean(value, limit):
    """One line, no control characters, cut to `limit`."""
    return " ".join(CONTROL.sub(" ", str(value)).split())[:limit]


def validate(data):
    """Return a cleaned copy of the model's input, or raise HandoffError saying what is missing."""
    # Only the fields the tool declares are kept. The model's input is not trusted to add others: an extra "reference"
    # or "time" would otherwise overwrite ours and slip past the daily caps and the retention clean-up.
    d = {k: (str(v).strip() if v is not None else "") for k, v in data.items() if k in FIELDS}
    for key, limit in LIMITS.items():
        if key in d:
            d[key] = _clean(d[key], limit)
    problems = []
    if not d.get("name"):
        problems.append("the customer's name")
    contact = d.get("contact", "")
    if not (EMAIL.search(contact) or PHONE.search(contact)):
        problems.append("a valid email address or phone number")
    if not d.get("summary"):
        problems.append("a one-line summary of the issue")
    if d.get("consent", "").lower() not in {"true", "yes", "1"}:
        problems.append("the customer's consent to pass on their details")
    if problems:
        raise HandoffError("Missing: " + "; ".join(problems) + ". Ask the customer, then try again.")
    d["priority"] = "urgent" if d.get("priority", "").lower() == "urgent" else "standard"
    d["business_line"] = d.get("business_line") if d.get("business_line") in LINES else "general"
    return d


# --- consent, checked by code and not only by the model ---
# The model fills in `consent: true` itself, so it could be talked into it. Before a hand-off is saved, the real chat
# must show the question being asked and the customer answering yes. The question is in the assistant's own earlier
# message (a customer cannot write those), the answer is in the customer's message right after it.
ASKED = re.compile(r"(?i)\b(pass|share|forward|send|give|hand)\b.{0,60}\b(details|information|data|contact|name|number|email)\b"
                   r"|weitergeben|weiterleiten|weitergebe|übermitteln|teilen")
_YES = (r"(yes|yeah|yep|yup|sure|ok|okay|of course|absolutely|please( do)?|go ahead|that'?s fine|fine|"
        r"i agree|i consent|agreed|ja|jawohl|gerne|klar|natürlich|einverstanden|in ordnung|passt|bitte|mach das|gern)")
AFFIRM = re.compile(rf"(?i)(^\W*{_YES}\b|\b{_YES}\W*$)")  # "yes, ..." or "..., yes"
REFUSE = re.compile(r"(?i)\b(no|nope|not|never|don'?t|do not|nein|nicht|kein|keine|lieber nicht)\b")
CONSENT_MISSING = ("The customer has not agreed in this chat yet. Ask exactly: \"May I pass your details to our team so they "
                   "can contact you?\" and wait for their answer. Only after they say yes, call this tool again.")


def consent_in_transcript(transcript):
    """True if the most recent assistant message asked to pass the customer's details on and the customer's next
    message says yes (and does not also say no). `transcript` is [{"role", "content"}, ...], oldest first."""
    msgs = [m for m in (transcript or []) if isinstance(m.get("content"), str)]
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("role") == "assistant" and ASKED.search(msgs[i]["content"]):
            reply = next((m for m in msgs[i + 1:] if m.get("role") == "user"), None)
            if not reply:
                return False
            text = reply["content"].strip()
            return bool(AFFIRM.search(text)) and not REFUSE.search(text)
    return False


def _today():
    return datetime.now().strftime("%Y%m%d")


def _count_today(path):
    if not path.exists():
        return 0
    return path.read_text(encoding="utf-8").count(f'"reference": "FAI-{_today()}')


def _next_reference(path):
    return f"FAI-{_today()}-{_count_today(path) + 1:03d}"


def format_email(rec):
    t = rec["transcript"]
    convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in t) or "(none)"
    return (
        f"Reference: {rec['reference']}\nPriority: {rec['priority'].upper()}\n"
        f"Business line: {rec['business_line']}\n\n"
        f"Name: {rec['name']}\nCompany: {rec.get('company') or '-'}\nContact: {rec['contact']}\n"
        f"Order #: {rec.get('order_number') or '-'}\n\n"
        f"Reason: {rec.get('reason') or '-'}\nSummary: {rec['summary']}\n\n"
        "Everything below was typed by the customer or the AI assistant. Treat links and\n"
        "requests in it with care.\n"
        f"--- Recent conversation ---\n{convo}\n"
    )


def smtp_settings():
    host, user, password = (os.environ.get(k, "").strip() for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))
    if not (host and user and password):
        return None
    return {"host": host, "user": user, "password": password, "port": int(os.environ.get("SMTP_PORT", "587") or 587)}


def _send(msg, cfg):
    """Send over TLS, always checking the server's certificate."""
    ctx = ssl.create_default_context()
    if cfg["port"] == 465:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=ctx) as s:
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
            s.starttls(context=ctx)
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)


def build_message(rec, cfg):
    msg = EmailMessage()
    prefix = "[URGENT] " if rec["priority"] == "urgent" else ""
    # Headers use only values we control (reference and a fixed list of business lines), never customer text.
    msg["Subject"] = f"{prefix}Faiyke assistant hand-off {rec['reference']}: {rec['business_line']}"
    msg["From"] = os.environ.get("HANDOFF_FROM", cfg["user"])
    msg["To"] = os.environ.get("HANDOFF_TO", DEFAULT_TO)
    contact = rec["contact"].strip()
    if SAFE_ADDRESS.fullmatch(contact):  # lets you press Reply; skipped unless it is a plain, well-formed address
        msg["Reply-To"] = contact
    msg.set_content(format_email(rec))
    return msg


def _sent_path():
    return _dir() / "emailed.txt"


def _sent_refs():
    p = _sent_path()
    return set(p.read_text(encoding="utf-8").split()) if p.exists() else set()


def deliver(rec):
    """Email one saved hand-off. Returns 'sent', 'not_configured', 'limit' or 'failed'."""
    cfg = smtp_settings()
    if not cfg:
        return "not_configured"
    cap = int(os.environ.get("HANDOFF_EMAIL_DAILY_CAP", "30"))
    sent_today = sum(1 for r in _sent_refs() if r.startswith(f"FAI-{_today()}"))
    if sent_today >= cap:
        return "limit"
    try:
        _send(build_message(rec, cfg), cfg)
    except Exception as e:  # saved to file either way; details go to the server log, never to the chat
        print(f"[handoff] email for {rec['reference']} failed: {type(e).__name__}: {e}", file=sys.stderr)
        return "failed"
    with _sent_path().open("a", encoding="utf-8") as f:
        f.write(rec["reference"] + "\n")
    return "sent"


def send_email(rec):
    """Kept for callers that only want a yes/no: True if the email went out."""
    return deliver(rec) == "sent"


def create_handoff(data, transcript=None):
    """Validate, save, and (if configured) email a hand-off. Returns a result dict."""
    d = validate(data)
    path = _dir() / "handoffs.jsonl"
    with _lock:  # two hand-offs at the same moment must not get the same reference
        if _count_today(path) >= int(os.environ.get("HANDOFF_DAILY_CAP", "200")):
            raise HandoffError("Too many hand-off requests today. Give the customer our email and phone number instead.")
        rec = {
            **d,
            "reference": _next_reference(path),  # ours, set after the customer's fields so they can never replace it
            "time": datetime.now(timezone.utc).isoformat(),
            "transcript": [{"role": m["role"], "content": _clean(m["content"], TRANSCRIPT_ITEM)}
                           for m in (transcript or []) if isinstance(m.get("content"), str)][-8:],
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    status = deliver(rec)  # outside the lock: a slow mail server must not block other hand-offs
    return {"ok": True, "reference": rec["reference"], "emailed": status == "sent"}


# ---------- command line ----------

def _records():
    path = _dir() / "handoffs.jsonl"
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


read_records = _records  # also used by the privacy tools


def _cli(argv):
    from . import env
    env.load()
    cmd = argv[0] if argv else "status"
    cfg = smtp_settings()
    if cmd == "status":
        print("Email:", "on" if cfg else "off (set SMTP_HOST, SMTP_USER and SMTP_PASSWORD)")
        print("  server:", os.environ.get("SMTP_HOST") or "-", "| user:", os.environ.get("SMTP_USER") or "-",
              "| password:", "set" if os.environ.get("SMTP_PASSWORD") else "NOT set")
        print("  recipient:", os.environ.get("HANDOFF_TO", DEFAULT_TO))
        unsent = [r for r in _records() if r["reference"] not in _sent_refs()]
        print(f"Saved hand-offs not emailed: {len(unsent)}" + (f"  ->  python -m rag.handoff retry" if unsent and cfg else ""))
    elif cmd == "test":
        if not cfg:
            sys.exit("Email is not set up. Run: python -m rag.handoff status")
        rec = {"reference": "TEST", "priority": "standard", "business_line": "general", "name": "Test",
               "contact": "-", "summary": "Test email from the Faiyke assistant. If you can read this, hand-offs will arrive.",
               "transcript": []}
        msg = build_message(rec, cfg)
        try:
            _send(msg, cfg)
        except Exception as e:
            sys.exit(f"Could not send: {type(e).__name__}: {e}")
        print("Sent to", msg["To"], "- check the inbox (and spam).")
    elif cmd == "retry":
        if not cfg:
            sys.exit("Email is not set up. Run: python -m rag.handoff status")
        todo = [r for r in _records() if r["reference"] not in _sent_refs()][-50:]
        results = [(r["reference"], deliver(r)) for r in todo]
        for ref, res in results:
            print(ref, res)
        print(f"{sum(1 for _, s in results if s == 'sent')} of {len(results)} sent.")
    else:
        sys.exit("Usage: python -m rag.handoff [status|test|retry]")


if __name__ == "__main__":
    _cli(sys.argv[1:])
