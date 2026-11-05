"""Web chat + WhatsApp server (standard library only).

    python -m rag.server            # http://127.0.0.1:8080

Endpoints
    GET  /                      demo page with the chat widget
    GET  /widget.js             the embeddable chat widget
    GET  /api/config            {"booking_url": "https://..." or null}
    POST /api/chat              {"session_id": "...", "message": "..."} -> {"session_id", "reply", "fid"}
    POST /api/chat/stream       same request; the answer arrives piece by piece (Server-Sent Events)
    POST /api/feedback          {"session_id": "...", "fid": "...", "rating": "up"|"down", "comment": "..."}
    POST /api/forget            {"session_id": "..."}  erase this chat's server-side data (see rag/privacy.py)
    GET  /admin                 login + dashboard (404 unless ADMIN_PASSWORD is set; see rag/admin.py)
    GET  /health
    GET  /webhook/whatsapp      Meta webhook verification
    POST /webhook/whatsapp      incoming WhatsApp messages (signature checked)

Configuration (environment variables)
    ANTHROPIC_API_KEY           required
    HOST / PORT                 default 127.0.0.1 / 8080
    ALLOWED_ORIGINS             comma list of websites allowed to embed the widget, e.g. https://faiyke.com
    RATE_LIMIT_PER_MIN          messages per IP per minute (default 15)
    DAILY_MESSAGE_CAP           stop answering after this many messages a day (default 2000; protects your bill)
    BOOKING_URL                 optional https link for "Book a call" (see rag/booking.py)
    PRIVACY_URL                 optional https link to your privacy policy, shown in the chat
    MAX_STREAMS                 answers streamed at the same time (default 40; more get "busy")
    ADMIN_PASSWORD              turns on the /admin dashboard (12+ characters; see rag/admin.py)
    LOG_GAPS                    "off" stops saving unanswered questions (see rag/gaps.py)
    RETENTION_*_DAYS            how long hand-offs / feedback / logs are kept (see rag/privacy.py)
    PER_VISITOR_DAILY_SHARE     percent of DAILY_MESSAGE_CAP one visitor may use per day (default 10)
    TRUSTED_PROXIES             proxy addresses whose X-Forwarded-For is believed (default 127.0.0.1,::1; "none" = no proxy)
    ALLOWED_HOSTS               comma list of site names /admin may be opened under, e.g. chat.faiyke.com,127.0.0.1,localhost
                                (default: no check; set it on a server)
    ADMIN_ALLOWED_IPS           comma list of addresses/networks that may open /admin (default: no restriction)
    FEEDBACK_RATE_PER_MIN       ratings per IP per minute (default 10)
    FEEDBACK_DAILY_CAP          ratings stored per day (default 500)
    FEEDBACK_DIR                where feedback/feedback.jsonl is kept
    WHATSAPP_TOKEN              permanent access token from Meta
    WHATSAPP_PHONE_ID           WhatsApp Business phone number ID
    WHATSAPP_VERIFY_TOKEN       any secret string you also enter in the Meta webhook settings
    WHATSAPP_APP_SECRET         Meta app secret (used to verify that webhooks really come from Meta)
"""
import base64
import contextlib
import hashlib
import hmac
import io
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import admin, booking, claude, env, feedback, gaps, metrics, netaddr, privacy, sessionstore, sourcelabels
from .assistant import Assistant
from .ingest import INDEX_PATH, ROOT, main as build_index
from .retrieve import Index

WEB_DIR = ROOT / "web"
MAX_MESSAGE_CHARS = 1000
SESSION_TTL = 30 * 60
MAX_SESSIONS = 500
GRAPH_URL = "https://graph.facebook.com/v21.0/{phone_id}/messages"
FALLBACK = (
    "Sorry, something went wrong on our side. Please email info@faiyke.com or call/WhatsApp +49 176 41565516 "
    "(Mon–Fri 8:00–18:00, Sat 10:00–14:00)."
)
DISCLOSURE = "Hi, I'm Faiyke's AI assistant. I can answer questions and pass you to our team."


# ---------- helpers (pure, tested) ----------

class ClientGone(Exception):
    """The customer closed the page or stopped reading while an answer was being streamed."""


class RateLimiter:
    def __init__(self, per_minute):
        self.per_minute, self.hits, self.lock = per_minute, {}, threading.Lock()

    def allow(self, key, now=None):
        now = time.time() if now is None else now
        with self.lock:
            if len(self.hits) > 50_000:  # bound memory: drop addresses with no recent hits
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < 60}
            recent = [t for t in self.hits.get(key, []) if now - t < 60]
            if len(recent) >= self.per_minute:
                self.hits[key] = recent
                return False
            self.hits[key] = recent + [now]
            return True


class DailyCap:
    """A daily total, plus (when `key` is given) a share of it per visitor, so one visitor or bot cannot use up the
    whole day's messages and leave everyone else with the fallback answer. `per_key` defaults to 10% of the total
    (PER_VISITOR_DAILY_SHARE, a percentage); a visitor who hits their share is refused without costing the total."""
    MAX_KEYS = 50_000  # bounds memory when many addresses are used

    def __init__(self, cap, per_key=None):
        if per_key is None:
            share = float(os.environ.get("PER_VISITOR_DAILY_SHARE", "10") or 10)
            per_key = max(1, int(cap * min(max(share, 1), 100) / 100))
        self.cap, self.per_key, self.day, self.count, self.keys = cap, per_key, None, 0, {}
        self.lock = threading.Lock()

    def allow(self, today=None, key=None):
        today = today or time.strftime("%Y-%m-%d")
        with self.lock:
            if today != self.day:
                self.day, self.count, self.keys = today, 0, {}
            if self.count >= self.cap:
                return False
            if key is not None:
                used = self.keys.get(key, 0)
                if used >= self.per_key:
                    return False
                if used or len(self.keys) < self.MAX_KEYS:
                    self.keys[key] = used + 1
            self.count += 1
            return True


class Sessions:
    """One Assistant (with its own history) per chat, expired after 30 minutes of silence.

    With a `store` (rag/sessionstore.py) a copy of each chat is also kept on disk, so a chat continues after a
    restart. The in-memory dictionary stays the fast path; the store is read only when a chat is not in memory."""

    PURGE_EVERY = 60  # seconds between sweeps of expired chats in the store

    def __init__(self, index, store=None):
        self.index, self.items, self.lock, self.store = index, {}, threading.Lock(), store
        self.last_purge = 0.0

    def get(self, key, channel, now=None):
        now = time.time() if now is None else now
        with self.lock:
            for k in [k for k, v in self.items.items() if now - v["seen"] > SESSION_TTL]:
                del self.items[k]  # the stored copy expires on its own (see load/purge)
            if self.store and now - self.last_purge > self.PURGE_EVERY:
                self.last_purge = now
                self.store.purge(now)
            if len(self.items) >= MAX_SESSIONS and key not in self.items:
                oldest = min(self.items, key=lambda k: self.items[k]["seen"])
                del self.items[oldest]
            new = key not in self.items
            if new:
                bot = Assistant(index=self.index, channel=channel)
                item = {"bot": bot, "lock": threading.Lock()}
                saved = self.store.load(key, now) if self.store else None
                if saved and saved["channel"] == channel:  # a chat from before a restart: pick it up again
                    bot.history = saved["history"]
                    item["log"] = saved["log"]
                    new = False
                self.items[key] = item
            self.items[key]["seen"] = now
            return self.items[key]["bot"], self.items[key]["lock"], new

    def save(self, key, channel, now=None):
        """Write the chat's current state to the store (no-op without one)."""
        if not self.store:
            return
        with self.lock:
            item = self.items.get(key)
            if not item:
                return
            history = list(getattr(item["bot"], "history", []) or [])
            log = [{**e, "question": feedback.scrub(e.get("question", ""), 300)} for e in item.get("log", [])]
        self.store.save(key, channel, history, log, now)

    def remember(self, key, fid, question, sources):
        """Keep what each recent answer was about so a rating can be matched to it."""
        with self.lock:
            item = self.items.get(key)
            if item:
                log = item.setdefault("log", [])
                log.append({"fid": fid, "question": question, "sources": list(sources)})
                del log[:-30]

    def forget(self, key):
        """Drop a chat's saved conversation, in memory and on disk. Returns True if there was one."""
        with self.lock:
            had = self.items.pop(key, None) is not None
        if self.store:
            had = self.store.delete(key) or had
        return had

    def find(self, key, fid):
        with self.lock:
            log = self.items.get(key, {}).get("log")
        if log is None and self.store:  # right after a restart: the chat is on disk but not yet in memory
            saved = self.store.load(key)
            log = saved["log"] if saved else []
        for entry in reversed(list(log or [])):
            if entry["fid"] == fid:
                return dict(entry)
        return None


SESSION_ID = re.compile(r"[0-9a-f]{32}")  # what the server issues (uuid4 hex); a guessable client-chosen id is refused


def valid_sid(sid):
    return isinstance(sid, str) and bool(SESSION_ID.fullmatch(sid))


def parse_json_object(raw):
    """The request body as a dict, or None if it is not JSON, is too deeply nested, or is not an object."""
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):  # bad JSON, bad UTF-8, or "[[[[..." nested past Python's limit
        return None
    return data if isinstance(data, dict) else None


INLINE_SCRIPT = re.compile(rb"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)


def page_csp(html):
    """The Content-Security-Policy for one of our pages. Scripts may run only if they come from this server or are
    one of the page's own inline scripts, named by their hash: an attacker who gets text into the page (a cross-site
    scripting hole) cannot add a script, because its hash is not on the list. Styles still allow inline rules."""
    # Browsers turn CRLF and lone CR into LF before they check an inline script against its hash, so the hash must be
    # taken over the same text. (A file saved with Windows line endings is otherwise blocked entirely.)
    def digest(text):
        text = text.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        return base64.b64encode(hashlib.sha256(text).digest()).decode()
    hashes = " ".join(f"'sha256-{digest(m.group(1))}'" for m in INLINE_SCRIPT.finditer(html))
    return (f"default-src 'self'; script-src 'self' {hashes}".rstrip() + "; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self'; object-src 'none'")


def verify_signature(secret, body, header):
    """Check Meta's X-Hub-Signature-256 header against the raw request body."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


def parse_whatsapp(payload):
    """Return [(message_id, sender_number, text_or_None)] from a webhook payload."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for m in change.get("value", {}).get("messages", []):
                if not isinstance(m, dict):
                    continue
                try:  # Meta's timestamp is in seconds; a signed message older than 10 minutes is a replay, not a retry
                    if time.time() - int(m.get("timestamp")) > 600:
                        continue
                except (TypeError, ValueError):
                    pass
                body = m.get("text")
                text = body.get("body") if m.get("type") == "text" and isinstance(body, dict) else None
                out.append((str(m.get("id", "")), str(m.get("from", "")), text if isinstance(text, str) else None))
    return out


def split_message(text, limit=3500):
    """Split a long reply into WhatsApp-sized pieces at paragraph or line breaks."""
    parts = []
    while len(text) > limit:
        cut = max(text.rfind("\n\n", 0, limit), text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
        cut = cut if cut > 0 else limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


def send_whatsapp(to, text):
    token, phone_id = os.environ.get("WHATSAPP_TOKEN"), os.environ.get("WHATSAPP_PHONE_ID")
    if not (token and phone_id):
        raise RuntimeError("WHATSAPP_TOKEN / WHATSAPP_PHONE_ID not set")
    for part in split_message(text):
        body = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": part}}
        req = urllib.request.Request(
            GRAPH_URL.format(phone_id=phone_id), data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=20).read()


# ---------- server ----------

class App:
    def __init__(self):
        if not INDEX_PATH.exists():
            build_index()
        self.sessions = Sessions(Index.load(), store=sessionstore.open_default())
        self.limiter = RateLimiter(int(os.environ.get("RATE_LIMIT_PER_MIN", "15")))
        self.cap = DailyCap(int(os.environ.get("DAILY_MESSAGE_CAP", "2000")))
        self.origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
        self.seen_wa = {}  # message id -> time, to ignore Meta's retries
        self.wa_lock = threading.Lock()
        self.booking = booking.booking_url()
        self.privacy_url = privacy.privacy_url()
        self.streams = threading.BoundedSemaphore(int(os.environ.get("MAX_STREAMS", "40")))  # answers being streamed at once
        self.admin = admin.Admin()  # off unless ADMIN_PASSWORD is set to something strong
        self.metrics = metrics.open_default()  # counts and times per day for the dashboard (no personal data)
        self.reindex_lock = threading.Lock()
        self.reindex_state = {}  # running, or the result of the last re-index started from the dashboard
        self.reindex_thread = None
        self.gaps = gaps.GapStore() if gaps.enabled() else None
        self.forget_limiter = RateLimiter(int(os.environ.get("FORGET_RATE_PER_MIN", "5")))
        self.fb_limiter = RateLimiter(int(os.environ.get("FEEDBACK_RATE_PER_MIN", "10")))
        self.feedback = feedback.FeedbackStore(daily_cap=int(os.environ.get("FEEDBACK_DAILY_CAP", "500")))

    def reply(self, key, channel, text, note="", on_event=None):
        """Ask the assistant. With `on_event` the answer is streamed (see Assistant.ask); ClientGone ends it early."""
        bot, lock, new = self.sessions.get(key, channel)
        with lock:
            offered, suggestions = False, []
            started, failed, sources, unsure = time.time(), False, [], False
            try:
                answer, sources, _ = bot.ask(text, note, on_event=on_event) if on_event else bot.ask(text, note)
                offered = bool(getattr(bot, "offered_booking", False))
                suggestions = list(getattr(bot, "suggestions", []) or [])
                # no match, an unconfirmed topic, or the model said it did not know (but not right after a hand-off)
                unsure = bool(getattr(bot, "gap", "")) and not getattr(bot, "handed_off", False)
                self.sessions.remember(key, feedback.answer_id(answer), text, sources)
                self.sessions.save(key, channel)
                if self.gaps and getattr(bot, "gap", ""):
                    self.gaps.record(bot.gap, text, key, sources)
            except ClientGone:
                raise  # the customer left: stop, and do not count a half-finished answer
            except Exception as e:
                print(f"[error] {type(e).__name__}: {e}", file=sys.stderr)
                answer, failed = FALLBACK, True
            if self.metrics:
                self.metrics.record(channel, time.time() - started, gap="" if failed else getattr(bot, "gap", "") or "",
                                    sources=sources if not failed else (), error=failed)
        # What the page shows besides the text: which parts of our information the answer used, and whether the
        # assistant was unsure (the page then offers a person). Nothing here comes from the customer.
        extra = {"sources": [] if failed else sourcelabels.labels(sources), "unsure": unsure and not failed}
        return answer, new, offered, suggestions, extra

    REINDEX_MIN_GAP = 10  # seconds between two re-indexes

    def reindex_start(self):
        """Start a re-index in the background (it takes about a minute, mostly for the semantic vectors) and return
        at once. Returns (started, message). The dashboard shows the progress and the result."""
        if self.reindex_lock.locked():
            return False, "A re-index is already running."
        self.reindex_thread = threading.Thread(target=self.reindex, name="reindex", daemon=True)
        self.reindex_thread.start()
        return True, "Re-index started."

    def reindex(self):
        """Rebuild the search index from knowledge-base/ and start using it for new chats.
        Returns (ok, message). One at a time; never raises."""
        if not self.reindex_lock.acquire(blocking=False):
            return False, "A re-index is already running."
        try:
            since = time.time() - self.reindex_state.get("finished", 0)
            if since < self.REINDEX_MIN_GAP:
                return False, "A re-index just finished. Wait a few seconds."
            out = io.StringIO()
            self.reindex_state = {"running": True, "started": time.time(), "finished": self.reindex_state.get("finished", 0)}
            try:
                with contextlib.redirect_stdout(out):
                    build_index()
                    new_index = Index.load()
                self.sessions.index = new_index  # chats that start from now on use it; open chats keep theirs
                lines = [l.strip() for l in out.getvalue().splitlines() if l.strip()]
                ok, message = True, (lines[0].split(" -> ")[0] if lines else "Index rebuilt.")  # no file path on the page
            except Exception as e:
                ok, message = False, f"Re-index failed: {type(e).__name__}: {e}"
                print(f"[reindex] {message}", file=sys.stderr)
            self.reindex_state = {"ok": ok, "message": message[:300], "finished": time.time()}
            return ok, message
        finally:
            self.reindex_lock.release()

    def handle_whatsapp(self, payload):
        for msg_id, sender, text in parse_whatsapp(payload):
            if not msg_id:
                continue  # without an id retries cannot be told apart, and "" would block every later message
            with self.wa_lock:
                now = time.time()
                self.seen_wa = {k: t for k, t in self.seen_wa.items() if now - t < 3600}
                if msg_id in self.seen_wa:
                    continue
                self.seen_wa[msg_id] = now
            try:
                if text is None:
                    send_whatsapp(sender, "I can only read text messages. Please type your question.")
                elif not self.limiter.allow(f"wa:{sender}"):
                    continue
                elif not self.cap.allow(key=f"wa:{sender}"):
                    send_whatsapp(sender, FALLBACK)
                else:
                    answer, new, _, _, _ = self.reply(f"wa:{sender}", "whatsapp", text[:MAX_MESSAGE_CHARS],
                                                   note=f"[Customer's WhatsApp number: +{sender}]")
                    if new:
                        send_whatsapp(sender, DISCLOSURE)
                    send_whatsapp(sender, answer)
            except Exception as e:
                print(f"[whatsapp error] {type(e).__name__}: {e}", file=sys.stderr)


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FaiykeAssistant"
        sys_version = ""  # do not announce the Python version
        timeout = 30  # seconds a client may stall while we read its request or write to it (slow-client protection)

        def log_message(self, fmt, *args):  # never log message content
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

        # --- plumbing
        def cors(self):
            origin = self.headers.get("Origin", "")
            if origin and origin in app.origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

        def send(self, code, body, ctype="application/json", extra_cors=True):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or "json" in ctype else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            if ctype == "text/html":  # the chat page itself: refuse framing (clickjacking), limit what it can load or do
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Permissions-Policy", "microphone=(self), camera=(), geolocation=()")
                self.send_header("Content-Security-Policy", page_csp(data))
            if extra_cors:
                self.cors()
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, code, obj):
            self.send(code, json.dumps(obj, ensure_ascii=False))

        def body(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:  # "abc": treat as no body instead of an unhandled error
                n = 0
            # a negative length would make read() wait for the connection to close
            return self.rfile.read(max(0, min(n, 100_000)))

        def client_ip(self):
            # X-Forwarded-For is believed only from a trusted proxy (rag/netaddr.py); anyone else can fake it.
            return netaddr.client_ip(self.client_address[0], self.headers.get("X-Forwarded-For", ""))

        # --- routes
        ROUTES = {"/health": "GET", "/api/config": "GET", "/": "GET", "/index.html": "GET", "/cookies": "GET",
                  "/cookies.html": "GET", "/widget.js": "GET", "/api/chat": "POST", "/api/chat/stream": "POST",
                  "/api/feedback": "POST", "/api/forget": "POST", "/webhook/whatsapp": "GET, POST"}

        def wrong_method(self, path):
            """405 with an Allow header when the path exists under another method. Returns True if it answered."""
            allowed = self.ROUTES.get(path)
            if not allowed:
                return False
            data = b'{"error": "method not allowed"}'
            self.send_response(405)
            for k, v in (("Allow", allowed), ("Content-Type", "application/json"), ("Content-Length", str(len(data))),
                         ("X-Content-Type-Options", "nosniff")):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)
            return True

        def other_method(self):
            path = urllib.parse.urlparse(self.path).path
            if not self.wrong_method(path):
                self.send(404, "not found", "text/plain", extra_cors=False)

        do_PUT = do_DELETE = do_PATCH = do_HEAD = other_method

        def do_OPTIONS(self):
            path = urllib.parse.urlparse(self.path).path
            if path not in self.ROUTES:
                return self.send(404, "not found", "text/plain", extra_cors=False)
            self.send_response(204)
            self.cors()
            self.end_headers()

        # --- admin dashboard (rag/admin.py): no CORS, never cached, answers 404 while switched off
        def admin_send(self, code, body, extra=()):
            data = body.encode("utf-8")
            self.send_response(code)
            for k, v in (("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(data))),
                         ("X-Content-Type-Options", "nosniff"), ("Cache-Control", "no-store"), ("Pragma", "no-cache"),
                         ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer"),
                         ("X-Robots-Tag", "noindex, nofollow"), ("Content-Security-Policy", admin.CSP), *extra):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def admin_same_site(self):
            origin = self.headers.get("Origin", "")
            host = self.headers.get("Host", "")
            return not origin or origin in (f"http://{host}", f"https://{host}")

        def admin_allowed(self):
            """ADMIN_ALLOWED_IPS, when set, limits the dashboard to those addresses; everyone else gets "not found"."""
            return netaddr.allowed(self.client_ip()) and netaddr.host_allowed(self.headers.get("Host"))

        def admin_get(self, path, query=""):
            if not app.admin.enabled or not self.admin_allowed() or path not in ("/admin", "/admin/"):
                return self.send(404, "not found", "text/plain", extra_cors=False)
            session = app.admin.check(admin.token_from_cookie_header(self.headers.get("Cookie")))
            if not session:
                return self.admin_send(200, admin.render_login())
            days = admin.parse_days(urllib.parse.parse_qs(query).get("days", [""])[0])
            self.admin_send(200, admin.render_dashboard(admin.collect(app, days=days), session["csrf"]))

        def admin_post(self, path, raw):
            if not app.admin.enabled or not self.admin_allowed() or path not in ("/admin/login", "/admin/logout", "/admin/reindex"):
                return self.send(404, "not found", "text/plain", extra_cors=False)
            if len(raw) > 2000:
                return self.send(413, "request too large", "text/plain", extra_cors=False)
            if not self.admin_same_site():
                return self.send(403, "forbidden", "text/plain", extra_cors=False)
            form = urllib.parse.parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
            secure = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
            token = admin.token_from_cookie_header(self.headers.get("Cookie"))
            if path == "/admin/login":
                # The visitor's real address: X-Forwarded-For counts only when it comes from our own proxy (netaddr.py).
                # Using the raw connection address would make every visitor look like the proxy (127.0.0.1), so anyone
                # could lock the owner out with five wrong passwords.
                status, value = app.admin.login(self.client_ip(), (form.get("password") or [""])[0])
                if status == "locked":
                    return self.admin_send(429, admin.render_login(locked_for=value), [("Retry-After", str(value))])
                if status == "bad":
                    time.sleep(admin.FAIL_DELAY)
                    return self.admin_send(401, admin.render_login("Wrong password."))
                return self.admin_send(303, "", [("Location", "/admin"), ("Set-Cookie", admin.cookie_header(value, secure))])
            session = app.admin.check(token)
            given = (form.get("csrf") or [""])[0]
            if not session or not hmac.compare_digest(given.encode(), session["csrf"].encode()):
                return self.send(403, "forbidden", "text/plain", extra_cors=False)
            if path == "/admin/reindex":  # the dashboard's one action: needs the login, the secret token and a same-site request
                app.reindex_start()
                return self.admin_send(303, "", [("Location", "/admin")])
            app.admin.logout(token)
            self.admin_send(303, "", [("Location", "/admin"), ("Set-Cookie", admin.cookie_header("", secure, clear=True))])

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path.startswith("/admin"):
                return self.admin_get(url.path, url.query)
            if url.path == "/health":
                return self.send_json(200, {"ok": True})
            if url.path == "/api/config":  # public settings the page needs; nothing secret belongs here
                return self.send_json(200, {"booking_url": app.booking, "privacy_url": app.privacy_url})
            if url.path in ("/", "/index.html"):
                return self.send(200, (WEB_DIR / "index.html").read_bytes(), "text/html", extra_cors=False)
            if url.path in ("/cookies", "/cookies.html"):
                return self.send(200, (WEB_DIR / "cookies.html").read_bytes(), "text/html", extra_cors=False)
            if url.path == "/widget.js":
                return self.send(200, (WEB_DIR / "widget.js").read_bytes(), "application/javascript")
            if url.path == "/webhook/whatsapp":
                q = urllib.parse.parse_qs(url.query)
                token = os.environ.get("WHATSAPP_VERIFY_TOKEN")
                given = (q.get("hub.verify_token") or [""])[0]
                if token and q.get("hub.mode") == ["subscribe"] and hmac.compare_digest(given.encode(), token.encode()):
                    return self.send(200, q.get("hub.challenge", [""])[0], "text/plain", extra_cors=False)
                return self.send(403, "forbidden", "text/plain", extra_cors=False)
            if not self.wrong_method(url.path):
                self.send(404, "not found", "text/plain", extra_cors=False)

        POST_PATHS = ("/api/chat", "/api/chat/stream", "/api/feedback", "/api/forget", "/webhook/whatsapp")

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path
            if path not in self.POST_PATHS and not path.startswith("/admin"):
                if not self.wrong_method(path):
                    self.send(404, "not found", "text/plain", extra_cors=False)
                return
            raw = self.body()
            if path.startswith("/admin"):
                return self.admin_post(path, raw)
            if path == "/api/chat":
                return self.chat(raw)
            if path == "/api/chat/stream":
                return self.chat_stream(raw)
            if path == "/api/feedback":
                return self.feedback(raw)
            if path == "/api/forget":
                return self.forget(raw)
            if path == "/webhook/whatsapp":
                if not verify_signature(os.environ.get("WHATSAPP_APP_SECRET"), raw, self.headers.get("X-Hub-Signature-256")):
                    return self.send(403, "bad signature", "text/plain", extra_cors=False)
                try:
                    payload = json.loads(raw)
                except ValueError:
                    return self.send(400, "bad json", "text/plain", extra_cors=False)
                threading.Thread(target=app.handle_whatsapp, args=(payload,), daemon=True).start()
                return self.send(200, "ok", "text/plain", extra_cors=False)  # answer Meta immediately
            self.send(404, "not found", "text/plain", extra_cors=False)

        def origin_ok(self):
            origin = self.headers.get("Origin", "")
            return not origin or origin in app.origins or origin == f"http://{self.headers.get('Host', '')}"

        def forget(self, raw):
            """Erase this chat's data on the server: the saved conversation and the ratings given in it."""
            if not self.origin_ok():
                return self.send_json(403, {"error": "origin not allowed"})
            if len(raw) > 1000:
                return self.send_json(413, {"error": "request too large"})
            if not app.forget_limiter.allow(f"forget:{self.client_ip()}"):
                return self.send_json(429, {"error": "too many requests, please wait a moment"})
            data = parse_json_object(raw)
            if data is None:
                return self.send_json(400, {"error": "bad request"})
            sid = data.get("session_id")
            if not valid_sid(sid):
                return self.send_json(400, {"error": "bad session id"})
            app.sessions.forget(f"web:{sid}")
            app.feedback.forget(sid)
            if app.gaps:
                app.gaps.forget(f"web:{sid}")
            self.send_json(200, {"ok": True})  # the same answer whether or not anything was stored

        def feedback(self, raw):
            if not self.origin_ok():
                return self.send_json(403, {"error": "origin not allowed"})
            if len(raw) > feedback.MAX_BODY_BYTES:
                return self.send_json(413, {"error": "request too large"})
            if not app.fb_limiter.allow(f"fb:{self.client_ip()}"):
                return self.send_json(429, {"error": "too many requests, please wait a moment"})
            try:
                data = json.loads(raw)
                clean = feedback.validate(data)
            except (ValueError, RecursionError) as e:  # FeedbackError and bad JSON are both ValueError
                return self.send_json(400, {"error": str(e) if isinstance(e, feedback.FeedbackError) else "bad request"})
            sid = data.get("session_id")
            ok_sid = valid_sid(sid)
            context = app.sessions.find(f"web:{sid}", clean["fid"]) if ok_sid else None
            app.feedback.record(clean["rating"], clean["fid"], clean["comment"], sid if ok_sid else "", context)
            self.send_json(200, {"ok": True})  # same answer whether or not it was stored: nothing to probe

        def chat_checks(self, raw):
            """The checks every chat request must pass. Returns (message, session_id), or None after sending the error."""
            if not self.origin_ok():
                return self.send_json(403, {"error": "origin not allowed"})
            data = parse_json_object(raw)
            if data is None or not isinstance(data.get("message", ""), str):
                return self.send_json(400, {"error": "bad request"})
            message = data.get("message", "").strip()
            if not message:
                return self.send_json(400, {"error": "empty message"})
            if len(message) > MAX_MESSAGE_CHARS:
                return self.send_json(400, {"error": f"message too long (max {MAX_MESSAGE_CHARS} characters)"})
            if not app.limiter.allow(f"ip:{self.client_ip()}"):
                return self.send_json(429, {"error": "too many messages, please wait a moment"})
            if not app.cap.allow(key=f"ip:{self.client_ip()}"):
                return self.send_json(503, {"reply": FALLBACK})
            sid = data.get("session_id")
            if not valid_sid(sid):
                sid = uuid.uuid4().hex  # never adopt an id the client made up
            return message, sid

        def result_of(self, sid, answer, offered, suggestions=(), extra=None):
            # "next" are follow-up buttons. They were already checked by suggest.clean(); the fallback text never gets any.
            extra = extra or {}
            return {"session_id": sid, "reply": answer, "fid": feedback.answer_id(answer),
                    "book": bool(offered and app.booking), "next": [] if answer == FALLBACK else list(suggestions)[:3],
                    "sources": extra.get("sources", []), "unsure": bool(extra.get("unsure"))}

        def chat(self, raw):
            checked = self.chat_checks(raw)
            if not checked:
                return
            message, sid = checked
            answer, _, offered, suggestions, extra = app.reply(f"web:{sid}", "web", message)
            self.send_json(200, self.result_of(sid, answer, offered, suggestions, extra))

        def chat_stream(self, raw):
            """Same as /api/chat, but the answer arrives piece by piece (Server-Sent Events).
            Events: {"session_id"}, {"t": text}, {"reset": true}, and last {"done": <the /api/chat result>}."""
            checked = self.chat_checks(raw)
            if not checked:
                return
            message, sid = checked
            if not app.streams.acquire(blocking=False):  # too many answers being written at once
                return self.send_json(503, {"error": "busy, please try again in a moment"})
            try:
                self.send_response(200)
                for k, v in (("Content-Type", "text/event-stream; charset=utf-8"), ("Cache-Control", "no-store"),
                             ("X-Accel-Buffering", "no"), ("X-Content-Type-Options", "nosniff")):
                    self.send_header(k, v)
                self.cors()
                self.end_headers()

                def emit(obj):
                    try:
                        self.wfile.write(b"data: " + json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n\n")
                        self.wfile.flush()
                    except OSError:  # includes broken pipe, reset and write timeout
                        raise ClientGone()

                def on_event(kind, payload):
                    if kind == "text":
                        emit({"t": payload})
                    elif kind == "sources":  # which parts of our information are being read (titles only)
                        emit({"src": payload})
                    else:
                        emit({"reset": True})
                try:
                    emit({"session_id": sid})
                    answer, _, offered, suggestions, extra = app.reply(f"web:{sid}", "web", message, on_event=on_event)
                    emit({"done": self.result_of(sid, answer, offered, suggestions, extra)})
                except ClientGone:
                    return  # nobody is listening any more
            finally:
                app.streams.release()

    return Handler


def main():
    env.load()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY first.")
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8080"))
    app = App()
    privacy.start_background()  # delete records past their retention period now, then once a day
    server = ThreadingHTTPServer((host, port), make_handler(app))
    wa = all(os.environ.get(k) for k in ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET"))
    print(f"Faiyke assistant on http://{host}:{port}   web chat: on   WhatsApp: {'on' if wa else 'off (not configured)'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
