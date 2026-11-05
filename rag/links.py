"""Links in the assistant's answers: only your own addresses stay clickable.

The model writes the answer, and a customer (or text a customer pasted in) can steer it. A phishing link that
looks like it comes from your shop is worse than a wrong answer, and WhatsApp turns every address in a message
into a tap-able link. So after the model has written its answer, any web address that is not yours is replaced
by "[link removed]".

Kept: faiyke.com and its subdomains, the host of BOOKING_URL and of PRIVACY_URL (both set by you in .env), and any
domain you add in LINK_ALLOWED_DOMAINS (comma list, subdomains included).
Not covered: a bare domain without http(s):// or www. (for example "evil.example/login"), and e-mail addresses.
"""
import os
import re
from urllib.parse import urlparse

OWN_DOMAINS = ("faiyke.com",)
REMOVED = "[link removed]"
URL = re.compile(r"(?i)(?:https?://|www\.)[^\s<>\"'\]]+")
TRAILING = ".,;:!?)"


def _host_of(url):
    try:
        return (urlparse(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def allowed_domains():
    domains = set(OWN_DOMAINS)
    for var in ("BOOKING_URL", "PRIVACY_URL"):
        host = _host_of(os.environ.get(var, "").strip())
        if host:
            domains.add(host)
    for d in os.environ.get("LINK_ALLOWED_DOMAINS", "").split(","):
        d = d.strip().lower().lstrip("*.")
        if d:
            domains.add(d)
    return domains


def host_allowed(host, domains=None):
    domains = allowed_domains() if domains is None else domains
    host = (host or "").lower().rstrip(".")
    return bool(host) and any(host == d or host.endswith("." + d) for d in domains)


def url_allowed(url, domains=None):
    """True if this web address points at one of your domains. `user@host` tricks and look-alike hosts such as
    faiyke.com.evil.example are judged by the real host, so they are refused."""
    url = url.strip()
    if url.lower().startswith("www."):
        url = "http://" + url
    return host_allowed(_host_of(url), domains)


def clean(text):
    """Replace every web address that is not yours with "[link removed]"."""
    if not text:
        return text
    domains = allowed_domains()

    def fix(m):
        raw = m.group(0)
        core = raw.rstrip(TRAILING)
        tail = raw[len(core):]
        return (core if url_allowed(core, domains) else REMOVED) + tail

    return URL.sub(fix, text)
