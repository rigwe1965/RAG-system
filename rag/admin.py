"""Admin dashboard: see what customers rate badly, what the assistant could not answer, and what was handed off.

    python -m rag.admin setup      # makes a strong password and shows the line to put in .env
    open  http://127.0.0.1:8080/admin

Off until ADMIN_PASSWORD is set in .env to something strong (12 or more characters). Without it the /admin
addresses answer "not found", so a scanner cannot even tell they exist. Put the server behind https before
you open the dashboard from anywhere but your own computer.

How it is protected (each point has a test):
  * No default password, and weak or short ones are refused (the dashboard stays off).
  * Failed logins are limited per address and overall, and answered slowly. The address is the real connection
    address, never the X-Forwarded-For header, which anyone could fake.
  * The login cookie is random, HttpOnly, SameSite=Strict, Secure on https, and expires (2 hours idle, 8 hours
    at most). Logging out ends it on the server. Log-out also needs a secret token and a same-site request.
  * The pages contain no JavaScript at all, a strict Content-Security-Policy forbids any, and everything customers
    typed is HTML-escaped. A malicious question cannot run code in your browser.
  * The dashboard reads, with one action: "Re-index now" (POST, needs the login, the secret token and a same-site
    request; one at a time). It cannot change or delete anything else. No CORS, no caching, no search-engine indexing.
  * Charts are inline SVG drawn on the server: still no JavaScript. The activity numbers (rag/metrics.py) are counts
    and times only, never questions, answers or contact details.
"""
import hashlib
import hmac
import html
import os
import re
import secrets
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

from . import feedback, handoff, metrics, privacy
from .ingest import INDEX_PATH, KB_DIR, PROMPT_FILES, SKIP_FILES

COOKIE = "fy_admin"
MIN_PASSWORD = 12
IDLE_SECONDS, MAX_SECONDS = 2 * 3600, 8 * 3600
WINDOW, PER_ADDRESS_MAX, OVERALL_MAX = 900, 5, 25  # failed logins allowed per 15 minutes
FAIL_DELAY = 0.4  # seconds a wrong password makes the caller wait
MAX_SESSIONS = 20
WEAK = {"password1234", "123456789012", "administrator", "changeme1234", "qwertyuiop12", "letmein12345",
        "adminadmin12", "welcome12345", "passwordpassword"}
ROWS = 20  # rows shown per table
RANGES = (7, 30, 90)  # days the dashboard can show
MIN_MESSAGES_FOR_UNUSED = 20  # fewer answers than this say nothing about which files are never used

CSP = ("default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; "
       "base-uri 'none'; img-src 'none'")


def password_problem(password):
    """Why this password is not acceptable, or '' if it is fine."""
    if not password:
        return "not set"
    if len(password) < MIN_PASSWORD:
        return f"shorter than {MIN_PASSWORD} characters"
    if len(set(password)) < 5 or password.lower() in WEAK:
        return "too easy to guess"
    return ""


class Admin:
    def __init__(self, password=None):
        password = os.environ.get("ADMIN_PASSWORD", "") if password is None else password
        self.problem = password_problem(password)
        self.enabled = not self.problem
        # Salted, deliberately slow hash (scrypt) instead of plain SHA-256: a guessed password costs real work, and the
        # comparison value is useless for anything else if the process memory is ever read.
        self._salt = secrets.token_bytes(16)
        self._digest = self._hash(password) if self.enabled else b""
        self.sessions = {}   # sha256(token) -> {"csrf", "created", "seen"}
        self.fails = {}      # address -> failure times
        self.all_fails = []  # failure times, all addresses together
        self.lock = threading.Lock()
        if password and self.problem:
            print(f"[admin] ADMIN_PASSWORD refused ({self.problem}); the dashboard is off", file=sys.stderr)

    # --- login
    def login(self, address, password, now=None):
        """Returns ("ok", token), ("bad", None) or ("locked", seconds_to_wait)."""
        now = time.time() if now is None else now
        with self.lock:
            mine = [t for t in self.fails.get(address, []) if now - t < WINDOW]
            self.all_fails = [t for t in self.all_fails if now - t < WINDOW]
            self.fails[address] = mine
            if len(mine) >= PER_ADDRESS_MAX or len(self.all_fails) >= OVERALL_MAX:
                oldest = min(mine) if len(mine) >= PER_ADDRESS_MAX else min(self.all_fails)
                return "locked", max(1, int(WINDOW - (now - oldest)))
        ok = hmac.compare_digest(self._hash((password or "")[:1000]), self._digest)
        with self.lock:
            if not ok:
                self.fails[address] = self.fails.get(address, []) + [now]
                self.all_fails.append(now)
                if len(self.fails) > 1000:  # do not let attackers grow this table without limit
                    self.fails = {a: v for a, v in self.fails.items() if any(now - t < WINDOW for t in v)}
                return "bad", None
            self.fails.pop(address, None)
            token = secrets.token_urlsafe(32)
            if len(self.sessions) >= MAX_SESSIONS:
                oldest_key = min(self.sessions, key=lambda k: self.sessions[k]["seen"])
                del self.sessions[oldest_key]
            self.sessions[self._key(token)] = {"csrf": secrets.token_urlsafe(24), "created": now, "seen": now}
            return "ok", token

    def _hash(self, password):
        return hashlib.scrypt(password.encode("utf-8"), salt=self._salt, n=2 ** 14, r=8, p=1, dklen=32)

    @staticmethod
    def _key(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def check(self, token, now=None):
        """The session for this cookie value, or None if it is unknown or expired."""
        if not self.enabled or not token:
            return None
        now = time.time() if now is None else now
        with self.lock:
            s = self.sessions.get(self._key(token))
            if not s:
                return None
            if now - s["seen"] > IDLE_SECONDS or now - s["created"] > MAX_SECONDS:
                del self.sessions[self._key(token)]
                return None
            s["seen"] = now
            return dict(s)

    def logout(self, token):
        with self.lock:
            self.sessions.pop(self._key(token or ""), None)


def token_from_cookie_header(header):
    try:
        jar = SimpleCookie()
        jar.load(header or "")
        return jar[COOKIE].value if COOKIE in jar else ""
    except Exception:
        return ""


def cookie_header(token, secure, clear=False):
    parts = [f"{COOKIE}={'' if clear else token}", "Path=/admin", "HttpOnly", "SameSite=Strict",
             "Max-Age=0" if clear else f"Max-Age={MAX_SECONDS}"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


# ---------- data ----------

def read_rows(path):
    import json
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except OSError:
        pass
    return rows


def _within(row, days, now):
    t = privacy._parse_time(row.get("time"))
    return t is not None and t >= now - timedelta(days=days)


def _norm_question(text):
    return " ".join(re.findall(r"\w+", str(text).lower()))[:80]


def parse_days(value):
    """The chosen range: 7, 30 or 90 days. Anything else means 30."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 30
    return n if n in RANGES else 30


def _local_day(value):
    t = privacy._parse_time(value)
    return t.astimezone().strftime("%Y-%m-%d") if t else None


def _per_day(rows, window, key=None):
    """Count rows per local day over `window` (list of day strings); `key(row)` may name a sub-count."""
    out = {d: Counter() for d in window}
    for r in rows:
        d = _local_day(r.get("time"))
        if d in out:
            out[d][key(r) if key else "n"] += 1
    return out


def kb_health(app):
    """How the knowledge base and its search index relate: when it was indexed and what changed since."""
    info = {"indexed_at": None, "changed": [], "files": 0, "chunks": 0, "unapproved": 0, "placeholders": 0, "indexed_files": []}
    try:
        info["indexed_at"] = INDEX_PATH.stat().st_mtime
        for path in KB_DIR.rglob("*.md"):
            rel = path.relative_to(KB_DIR).as_posix()
            if rel in SKIP_FILES or rel in PROMPT_FILES:
                continue
            if path.stat().st_mtime > info["indexed_at"] + 1:
                info["changed"].append(rel)
        info["changed"].sort()
    except OSError:
        pass
    chunks = getattr(app.sessions.index, "chunks", None) or []
    info["chunks"] = len(chunks)
    info["indexed_files"] = sorted({c["file"] for c in chunks})
    info["files"] = len(info["indexed_files"])
    info["unapproved"] = sum(1 for c in chunks if c.get("unapproved"))
    info["placeholders"] = sum(1 for c in chunks if c.get("placeholders"))
    return info


def collect(app, now=None, days=30):
    """Everything the dashboard shows, as plain data. `days` is the range for the charts and tables."""
    now = now or datetime.now(timezone.utc)
    days = parse_days(days)
    s = {"now": now, "days": days}
    window = metrics.days_back(days, now.timestamp())
    cap = app.cap
    s["messages_today"] = cap.count if cap.day == time.strftime("%Y-%m-%d") else 0
    s["message_cap"] = cap.cap
    s["active_chats"] = len(app.sessions.items)

    hand = handoff.read_records()
    sent = handoff._sent_refs()
    s["handoffs_7d"] = [h for h in hand if _within(h, 7, now)]
    in_range = [h for h in hand if _within(h, days, now)]
    s["handoffs_range"] = in_range
    s["handoffs_by_line"] = Counter(h.get("business_line") or "general" for h in in_range).most_common()
    s["handoffs_by_priority"] = Counter(h.get("priority") or "standard" for h in in_range)
    s["handoff_series"] = [{"day": d, "n": c["n"]} for d, c in _per_day(in_range, window).items()]
    s["handoffs_unsent"] = [h for h in hand if h.get("reference") not in sent]
    s["handoffs_recent"] = list(reversed(hand))[:ROWS]
    s["sent"] = sent

    latest = {}  # one vote per answer per chat: the last one counts
    for r in read_rows(app.feedback.path):
        if _within(r, days, now):
            latest[(r.get("session"), r.get("fid"))] = r
    votes = list(latest.values())
    s["up"] = sum(1 for v in votes if v.get("rating") == "up")
    s["down"] = sum(1 for v in votes if v.get("rating") == "down")
    downs = [v for v in votes if v.get("rating") == "down"]
    s["bad_files"] = Counter(f for v in downs for f in (v.get("sources") or [])).most_common(8)
    s["downs_recent"] = sorted(downs, key=lambda v: str(v.get("time")), reverse=True)[:ROWS]
    rated = _per_day(votes, window, key=lambda v: v.get("rating"))
    s["rating_series"] = [{"day": d, "up": c["up"], "down": c["down"]} for d, c in rated.items()]

    gap_rows = [g for g in read_rows(app.gaps.path) if _within(g, days, now)] if app.gaps else []
    s["gap_kinds"] = Counter(g.get("kind") for g in gap_rows)
    groups = {}
    for g in gap_rows:
        k = _norm_question(g.get("question", ""))
        if not k:
            continue
        e = groups.setdefault(k, {"count": 0, "sample": g.get("question", ""), "kind": g.get("kind"), "last": ""})
        e["count"] += 1
        e["last"] = max(e["last"], str(g.get("time")))
    newest_first = sorted(groups.values(), key=lambda e: e["last"], reverse=True)
    s["gap_top"] = sorted(newest_first, key=lambda e: -e["count"])[:ROWS]  # most frequent first, newest first among equals
    s["gaps_recent"] = sorted(gap_rows, key=lambda g: str(g.get("time")), reverse=True)[:ROWS]
    s["gaps_on"] = app.gaps is not None

    store = getattr(app, "metrics", None)
    s["metrics_on"] = store is not None
    s["activity"] = store.report(days, now.timestamp()) if store else None
    s["kb"] = kb_health(app)
    used = {f for f, _ in (s["activity"] or {}).get("files", [])}
    enough = bool(s["activity"]) and s["activity"]["messages"] >= MIN_MESSAGES_FOR_UNUSED
    s["files_unused"] = [f for f in s["kb"]["indexed_files"] if f not in used] if enough else None
    s["reindex"] = dict(getattr(app, "reindex_state", {}) or {})

    s["checks"] = [
        ("Handoff emails", "on" if handoff.smtp_settings() else "off: set SMTP_PASSWORD (python -m rag.handoff status)"),
        ("Booking link", "on" if app.booking else "off (BOOKING_URL not set)"),
        ("Privacy policy link", "on" if app.privacy_url else "off (PRIVACY_URL not set)"),
        ("Semantic search", "on" if getattr(app.sessions.index, "vectors", None) is not None else "off (keyword search only)"),
        ("Knowledge gaps log", "on" if app.gaps else "off (LOG_GAPS=off)"),
        ("Listening on", os.environ.get("HOST", "127.0.0.1") + (" (this computer only)" if os.environ.get("HOST", "127.0.0.1") == "127.0.0.1"
                                                                    else ": use https in front of it")),
        ("Automatic deletion (days)", f"handoffs {privacy.retention_days('RETENTION_HANDOFF_DAYS') or 'never'}, "
                                      f"feedback {privacy.retention_days('RETENTION_FEEDBACK_DAYS') or 'never'}, "
                                      f"gaps {privacy.retention_days('RETENTION_GAPS_DAYS') or 'never'}"),
    ]
    return s


# ---------- pages ----------

def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


STYLE = """
:root{--ink:#161513;--mute:#6a665f;--bg:#f1efea;--card:#fbfaf8;--line:#dcd8d0;--brand:#5a3b96;--accent:#ff6b1a;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--ink:#efece6;--mute:#a09b92;--bg:#141311;--card:#1c1b18;--line:#2e2c28;--brand:#b9a0f2;--accent:#ff7a2e;--bad:#f2877f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif}
main{max-width:1000px;margin:0 auto;padding:20px 16px 60px}
header{display:flex;align-items:center;gap:12px;margin-bottom:18px}header h1{font-size:24px;font-weight:700;letter-spacing:-.02em;margin:0;flex:1}
h2{font-size:16px;margin:30px 0 4px}p.sub{margin:0 0 10px;color:var(--mute);font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.tile b{display:block;font-size:28px;font-weight:700;letter-spacing:-.02em;line-height:1.2}.tile span{color:var(--mute);font-size:13px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
th{color:var(--mute);font-weight:600;font-size:12.5px}tr:last-child td{border-bottom:0}
.wrap{overflow-x:auto}.bad{color:var(--bad);font-weight:600}.ok{color:var(--accent);font-weight:600}.mute{color:var(--mute)}
button{font:inherit;border:0;border-radius:8px;padding:8px 14px;font-weight:600;background:var(--accent);color:#fff;cursor:pointer}
button.plain{background:none;color:var(--mute);border:1px solid var(--line)}
form.login{max-width:340px;margin:12vh auto 0;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px}
form.login h1{font-size:18px;margin:0 0 14px}form.login input{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:10px;font:inherit;margin:6px 0 14px;background:var(--bg);color:var(--ink)}
form.login p.err{color:var(--bad);margin:0 0 10px}
.range{display:flex;gap:6px;margin:0 0 14px}.range a{padding:5px 12px;border:1px solid var(--line);border-radius:999px;color:var(--mute);text-decoration:none;font-size:13.5px;background:var(--card)}
.range a.on{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.chart{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px 8px}.chart h3{font-size:14px;margin:0 0 2px}
.chart svg.plot{width:100%;height:auto;display:block}.chart svg.sw{width:10px;height:10px;display:inline-block;vertical-align:-1px}.chart .legend span{margin-right:10px}.chart text{fill:var(--mute);font-size:15px}.chart .legend{color:var(--mute);font-size:12.5px;margin:2px 0 6px}
.c-main{fill:var(--accent)}.c-bad{fill:var(--bad)}.c-brand{fill:var(--brand)}.c-grid{stroke:var(--line);stroke-width:1}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,430px),1fr));gap:10px;margin-top:10px}
.kb{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}.kb .txt{flex:1;min-width:240px}
form.inline{margin:0}.note{margin:8px 0 0;font-size:14px}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:0}dt{color:var(--mute)}dd{margin:0}
"""


def _page(title, body, refresh=0):
    again = f'<meta http-equiv="refresh" content="{int(refresh)}">' if refresh else ""  # plain HTML, no script
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{again}'
            f'<meta name="robots" content="noindex,nofollow"><meta name="color-scheme" content="light dark"><title>{esc(title)}</title>'
            f'<style>{STYLE}</style></head><body>{body}</body></html>')


def render_login(message="", locked_for=0):
    note = ""
    if locked_for:
        note = f'<p class="err">Too many wrong passwords. Try again in {max(1, locked_for // 60)} minute(s).</p>'
    elif message:
        note = f'<p class="err">{esc(message)}</p>'
    return _page("Admin login", (
        '<form class="login" method="post" action="/admin/login"><h1>Faiyke assistant admin</h1>' + note +
        '<label for="pw">Password</label><input id="pw" name="password" type="password" autocomplete="current-password" required autofocus>'
        '<button type="submit">Log in</button></form>'))


def _when(value):
    return esc(str(value or "")[:16].replace("T", " "))


def _table(headers, rows, empty):
    if not rows:
        return f'<p class="mute">{esc(empty)}</p>'
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="wrap"><table><tr>{head}</tr>{body}</table></div>'


def _bars(series, parts, title, empty_note=""):
    """A stacked bar chart per day as inline SVG (no JavaScript). `series` is a list of {"day", ...counts};
    `parts` is [(key, css class, label)] drawn bottom to top. Hovering a bar shows its numbers (native tooltip)."""
    width, height, left, bottom, top = 640, 170, 34, 24, 10
    totals = [sum(row.get(k, 0) for k, _, _ in parts) for row in series]
    peak = max(totals) if totals else 0
    legend = " ".join(f'<span><svg class="sw" viewBox="0 0 10 10" aria-hidden="true"><rect width="10" height="10" class="{c}"/></svg> {esc(l)}</span>'
                      for _, c, l in parts)
    head = f'<h3>{esc(title)}</h3><div class="legend">{legend}</div>'
    if not peak:
        return f'<div class="chart">{head}<p class="mute">{esc(empty_note or "No data in this period.")}</p></div>'
    step = peak if peak <= 4 else -(-peak // 4)  # grid line spacing
    n = len(series)
    slot = (width - left) / n
    bw = max(1.0, slot * 0.72)
    plot = height - bottom - top
    out = [f'<svg class="plot" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">']
    for g in range(0, peak + 1, max(1, step)):
        y = top + plot - plot * g / peak
        out.append(f'<line x1="{left}" x2="{width}" y1="{y:.1f}" y2="{y:.1f}" class="c-grid"/><text x="{left - 4}" y="{y + 3:.1f}" text-anchor="end">{g}</text>')
    for i, row in enumerate(series):
        x = left + i * slot + (slot - bw) / 2
        y = top + plot
        tip = esc(f"{row['day']}: " + ", ".join(f"{row.get(k, 0)} {l}" for k, _, l in parts))
        bars = []
        for k, c, _ in parts:
            v = row.get(k, 0)
            if v:
                h = plot * v / peak
                y -= h
                bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" class="{c}"/>')
        out.append(f"<g><title>{tip}</title>" + "".join(bars) + f'<rect x="{x:.1f}" y="{top}" width="{bw:.1f}" height="{plot}" fill="transparent"/></g>')
    first, last = series[0]["day"][5:], series[-1]["day"][5:]
    out.append(f'<text x="{left}" y="{height - 5}">{esc(first)}</text><text x="{width}" y="{height - 4}" text-anchor="end">{esc(last)}</text></svg>')
    return f'<div class="chart">{head}{"".join(out)}</div>'


def _secs(value):
    return "–" if value is None else (f"{value:.1f} s")


def render_dashboard(s, csrf):
    # Every value below that came from a customer or the assistant goes through esc().
    days = s.get("days", 30)
    act = s.get("activity")
    total = s["up"] + s["down"]
    liked = f"{round(100 * s['up'] / total)}% good" if total else "no ratings yet"
    tiles = [
        (f"{s['messages_today']} / {s['message_cap']}", "messages today (since the server started)"),
        (str(s["active_chats"]), "chats open now"),
    ]
    if act:
        tiles += [(str(act["messages"]), f"messages ({days} days)"),
                  (_secs(act["median_seconds"]), f"typical answer time (slowest 10%: {_secs(act['p90_seconds'])})"),
                  (str(act["errors"]), f"answers that failed ({days} days)")]
    tiles += [
        (str(len(s["handoffs_range"])), f"handoffs ({days} days)"),
        (str(len(s["handoffs_unsent"])), "handoffs not emailed"),
        (liked, f"{s['down']} bad, {s['up']} good answers ({days} days)"),
        (str(sum(s["gap_kinds"].values())), f"unanswered questions ({days} days)"),
    ]
    out = ['<main><header><h1>Faiyke assistant · Admin</h1>'
           f'<form method="post" action="/admin/logout"><input type="hidden" name="csrf" value="{esc(csrf)}">'
           '<button class="plain" type="submit">Log out</button></form></header>']
    out.append('<nav class="range" aria-label="Period">' + "".join(
        f'<a href="/admin?days={d}"{" class=on aria-current=page" if d == days else ""}>{d} days</a>' for d in RANGES) + "</nav>")
    out.append('<div class="tiles">' + "".join(
        f'<div class="tile"><b class="{"bad" if (label.startswith("handoffs not") or label.startswith("answers that failed")) and value != "0" else ""}">{esc(value)}</b><span>{esc(label)}</span></div>'
        for value, label in tiles) + "</div>")

    # --- activity over time
    out.append(f"<h2>Activity, last {days} days</h2>")
    if not s.get("metrics_on"):
        out.append('<p class="sub">The activity log is switched off (METRICS=off), so there are no charts of messages or answer times.</p>')
    elif not act["messages"]:
        out.append('<p class="sub">No messages counted yet in this period. The numbers fill in as customers chat; history starts from the first message after this feature was added.</p>')
    charts = []
    if act and act["messages"]:
        charts.append(_bars(act["days"], [("web", "c-main", "web"), ("whatsapp", "c-brand", "WhatsApp"), ("errors", "c-bad", "failed")], "Messages per day"))
    charts.append(_bars(s["rating_series"], [("up", "c-main", "good"), ("down", "c-bad", "bad")], "Ratings per day", "Nobody has rated an answer in this period."))
    charts.append(_bars(s["handoff_series"], [("n", "c-brand", "handoffs")], "Handoffs per day", "No handoffs in this period."))
    if act and act["messages"]:
        charts.append(_bars(act["days"], [("gaps", "c-bad", "unanswered")], "Unanswered questions per day", "Every question was answered."))
    out.append('<div class="grid2">' + "".join(charts) + "</div>")

    # --- knowledge base health + the re-index action
    kb = s["kb"]
    out.append("<h2>Knowledge base</h2>")
    when = datetime.fromtimestamp(kb["indexed_at"]).strftime("%Y-%m-%d %H:%M") if kb["indexed_at"] else "never"
    if kb["changed"]:
        shown = ", ".join(esc(f) for f in kb["changed"][:6]) + (f" and {len(kb['changed']) - 6} more" if len(kb["changed"]) > 6 else "")
        status = f'<span class="bad">{len(kb["changed"])} file(s) changed since the last index:</span> {shown}. Customers still get the old text until you re-index.'
    else:
        status = '<span class="ok">The index is up to date.</span>'
    out.append('<div class="kb"><div class="txt">'
               f"<div>{status}</div>"
               f'<div class="mute">Last indexed {esc(when)} · {kb["chunks"]} passages from {kb["files"]} files · '
               f'{kb["unapproved"]} still marked (PROPOSED), {kb["placeholders"]} with unfilled [placeholders]</div></div>'
               f'<form class="inline" method="post" action="/admin/reindex"><input type="hidden" name="csrf" value="{esc(csrf)}">'
               f'<button type="submit"{" disabled" if (s.get("reindex") or {}).get("running") else ""}>Re-index now</button></form></div>')
    ri = s.get("reindex") or {}
    running = bool(ri.get("running"))
    if running:
        secs = max(0, int(time.time() - ri.get("started", time.time())))
        out.append(f'<p class="note">Re-indexing since {secs} s. It takes about a minute. This page refreshes by itself.</p>')
    elif ri:
        out.append(f'<p class="note {"ok" if ri.get("ok") else "bad"}">{esc(ri.get("message"))}</p>')
    if s.get("files_unused") is not None:
        if s["files_unused"]:
            out.append(f'<p class="sub">Not used for any answer in {days} days (customers never asked about them, or search never finds them): '
                       + ", ".join(esc(f) for f in s["files_unused"]) + "</p>")
        else:
            out.append(f'<p class="sub">Every knowledge-base file was used for at least one answer in {days} days.</p>')
    elif s.get("metrics_on"):
        out.append(f'<p class="sub">Which files are never used will show here once at least {MIN_MESSAGES_FOR_UNUSED} answers are counted.</p>')
    if act and act["files"]:
        out.append(_table(["File", "Used in answers"], [[esc(f), esc(n)] for f, n in act["files"][:10]], ""))

    out.append("<h2>Questions the assistant could not answer</h2>")
    out.append('<p class="sub">Add these to the knowledge base, then press Re-index now. The most frequent come first.</p>')
    kinds = {"no_match": "nothing matched", "pending": "waiting for approval", "unanswered": "said it did not know"}
    out.append(_table(["Times", "Question", "Why", "Last"],
                      [[esc(e["count"]), esc(e["sample"]), esc(kinds.get(e["kind"], e["kind"])), _when(e["last"])] for e in s["gap_top"]],
                      "Nothing yet." if s["gaps_on"] else "The knowledge gaps log is switched off (LOG_GAPS=off)."))

    out.append("<h2>Answers customers rated bad</h2>")
    if s["bad_files"]:
        out.append('<p class="sub">Knowledge-base files behind them: ' + ", ".join(
            f"{esc(f)} ({n}×)" for f, n in s["bad_files"]) + "</p>")
    out.append(_table(["When", "Question", "Comment", "Files used"],
                      [[_when(v.get("time")), esc(v.get("question") or "(not saved)"), esc(v.get("comment")),
                        esc(", ".join(v.get("sources") or []))] for v in s["downs_recent"]], f"No bad ratings in the last {days} days."))

    out.append("<h2>Handoffs</h2>")
    if s["handoffs_by_line"]:
        out.append(f'<p class="sub">By business line, last {days} days: ' + ", ".join(
            f"{esc(line)} ({n})" for line, n in s["handoffs_by_line"]) +
            f" · urgent: {s['handoffs_by_priority'].get('urgent', 0)}</p>")
    out.append('<p class="sub">Latest handoffs. They contain the customers\u2019 contact details. Do not share this page.</p>')
    out.append(_table(["Reference", "When", "Priority", "Line", "Name", "Contact", "Summary", "Emailed"],
                      [[esc(h.get("reference")), _when(h.get("time")),
                        f'<span class="{"bad" if h.get("priority") == "urgent" else ""}">{esc(h.get("priority"))}</span>',
                        esc(h.get("business_line")), esc(h.get("name")), esc(h.get("contact")), esc(h.get("summary")),
                        '<span class="ok">yes</span>' if h.get("reference") in s["sent"] else '<span class="bad">no</span>']
                       for h in s["handoffs_recent"]], "No handoffs yet."))

    out.append("<h2>Setup</h2><dl>" + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in s["checks"]) + "</dl></main>")
    return _page("Admin · Faiyke assistant", "".join(out), refresh=5 if running else 0)


# ---------- command line ----------

def _cli(argv):
    cmd = argv[0] if argv else "setup"
    if cmd != "setup":
        sys.exit("Usage: python -m rag.admin setup")
    pw = secrets.token_urlsafe(18)
    print("Add this line to your .env file (keep it private), then restart the server:\n")
    print(f"ADMIN_PASSWORD={pw}\n")
    print("Then open http://127.0.0.1:8080/admin")


if __name__ == "__main__":
    _cli(sys.argv[1:])
