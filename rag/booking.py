"""Booking link ("Book a call"). Off until BOOKING_URL is set in .env.

    BOOKING_URL=https://calendly.com/your-name/intro-call

    python -m rag.booking          # check that the link is accepted

How it works, and why it is safe:
  * The AI model never sees or writes the link. When it offers a call it only adds the marker
    [[book]]. The server removes the marker. On the website the page shows a "Book a call"
    button (from /api/config); on WhatsApp the server adds the link text itself.
    So a manipulated model cannot produce a different link.
  * The link comes only from your .env file and must be a plain https address on a public
    domain: no javascript:/data: links, no passwords in it, no IP addresses, no localhost,
    no unusual ports, no spaces or quotes.
"""
import os
import re
import sys
from urllib.parse import urlsplit

MAX_URL = 300
MARKER = re.compile(r"[ \t]*\[\[\s*book\s*\]\][ \t]*", re.IGNORECASE)
HOST = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
BAD_CHARS = re.compile(r"[\x00-\x20\x7f\"'<>\\`^{}|]")
_warned = set()


def parse(url):
    """Return the cleaned URL, or raise ValueError saying what is wrong with it."""
    url = (url or "").strip()
    if not url:
        raise ValueError("empty")
    if len(url) > MAX_URL:
        raise ValueError(f"longer than {MAX_URL} characters")
    if BAD_CHARS.search(url):
        raise ValueError("contains spaces, quotes or other characters that are not allowed")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise ValueError("not a valid web address")
    if parts.scheme != "https":
        raise ValueError("must start with https://")
    if parts.username is not None or parts.password is not None:
        raise ValueError("must not contain a username or password")
    host = (parts.hostname or "").lower()
    if not HOST.match(host) or host.split(".")[-1].isdigit():
        raise ValueError("must use a public domain name (no IP address or localhost)")
    if port not in (None, 443):
        raise ValueError("must not use a custom port")
    return url


def booking_url():
    """The configured link, or None if it is not set or not acceptable (a warning is printed once)."""
    raw = os.environ.get("BOOKING_URL", "").strip()
    if not raw:
        return None
    try:
        return parse(raw)
    except ValueError as e:
        if raw not in _warned:
            _warned.add(raw)
            print(f"[booking] BOOKING_URL ignored: {e}", file=sys.stderr)
        return None


def process(answer, channel="web", url=None):
    """Remove the [[book]] marker from the model's answer.

    Returns (text, offered). `offered` is True only on the website when a link is configured.
    On WhatsApp the first marker becomes the link text.
    """
    if not MARKER.search(answer):
        return answer, False
    if channel == "whatsapp" and url:
        first = [True]

        def swap(_):
            if first[0]:
                first[0] = False
                return f"\n\nBook a call: {url}\n"
            return " "
        text = MARKER.sub(swap, answer)
    else:
        text = MARKER.sub(" ", answer)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, bool(url) and channel == "web"


RULES = (
    "# Booking\n"
    "Customers can book a call themselves. This replaces every 'no booking link yet' note above: "
    "ignore those notes. When you offer a call, a demo or an assessment, or the customer asks to book, "
    "say they can pick a time themselves and end that message with the exact marker [[book]] on its own line. "
    "Never write a web address yourself, and never use the marker for anything else. Collect the customer's "
    "name and contact for a hand-off as before if they also want a person to reach out."
)


if __name__ == "__main__":
    from . import env
    env.load()
    raw = os.environ.get("BOOKING_URL", "").strip()
    if not raw:
        print("Booking link is off. Add BOOKING_URL=https://... to .env to turn it on.")
    else:
        try:
            print("OK, the link will be used:", parse(raw))
        except ValueError as e:
            sys.exit(f"Not accepted: {e}")
