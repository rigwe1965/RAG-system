"""Helper for connecting WhatsApp. Run these after filling in .env.

    python -m rag.whatsapp_setup check                       # are all settings present, and does Meta accept them?
    python -m rag.whatsapp_setup send 4917612345678          # send Meta's "hello_world" test message
    python -m rag.whatsapp_setup webhook https://YOUR-URL    # does your public server answer Meta's verification?
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from . import env

REQUIRED = {
    "ANTHROPIC_API_KEY": "Claude API key (console.anthropic.com)",
    "WHATSAPP_TOKEN": "Meta access token (Business Settings > System users, or the temporary one on the API Setup page)",
    "WHATSAPP_PHONE_ID": "Phone number ID (WhatsApp > API Setup; a long number, NOT the phone number itself)",
    "WHATSAPP_VERIFY_TOKEN": "Any secret word you choose; you type the same one in Meta's webhook settings",
    "WHATSAPP_APP_SECRET": "App secret (App settings > Basic > Show)",
}
GRAPH = "https://graph.facebook.com/v21.0"


def missing(environ):
    return [k for k in REQUIRED if not environ.get(k)]


def _get(url, token=None, timeout=20):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8")


def check_webhook(base_url, verify_token, getter=_get):
    """Ask the public server the same question Meta asks. Returns (ok, message)."""
    challenge = "faiyke-test-12345"
    q = urllib.parse.urlencode({"hub.mode": "subscribe", "hub.verify_token": verify_token, "hub.challenge": challenge})
    url = base_url.rstrip("/") + "/webhook/whatsapp?" + q
    try:
        status, body = getter(url)
    except urllib.error.HTTPError as e:
        return False, f"Server answered {e.code}. A 403 means the verify token on the server differs from the one you used."
    except Exception as e:
        return False, f"Could not reach {base_url}: {e}. Is the server running, and is the tunnel/host up?"
    if status == 200 and body.strip() == challenge:
        return True, "OK: your server answers Meta's verification correctly."
    return False, f"Unexpected answer (status {status}): {body[:80]!r}"


def cmd_check():
    import os
    loaded = env.load()
    if loaded:
        print("Loaded from .env:", ", ".join(loaded))
    absent = missing(os.environ)
    for k, why in REQUIRED.items():
        print(f"  {'OK     ' if k not in absent else 'MISSING'} {k}" + (f"  <- {why}" if k in absent else ""))
    if absent:
        print("\nFill in the missing values in .env (see .env.example), then run this again.")
        return 1
    try:
        _, body = _get(f"{GRAPH}/{os.environ['WHATSAPP_PHONE_ID']}?fields=display_phone_number,verified_name,quality_rating",
                       os.environ["WHATSAPP_TOKEN"])
        info = json.loads(body)
        print(f"\nMeta accepts the token. WhatsApp number: {info.get('display_phone_number')}, "
              f"name: {info.get('verified_name')}, quality: {info.get('quality_rating')}")
        return 0
    except urllib.error.HTTPError as e:
        print(f"\nMeta rejected the request ({e.code}): {e.read().decode('utf-8', 'replace')[:300]}")
        print("Common causes: expired temporary token (they last about 24 hours), wrong phone number ID.")
        return 1
    except Exception as e:
        print(f"\nCould not reach Meta: {e}")
        return 1


def cmd_send(number):
    import os
    env.load()
    token, phone_id = os.environ.get("WHATSAPP_TOKEN"), os.environ.get("WHATSAPP_PHONE_ID")
    if not (token and phone_id):
        print("WHATSAPP_TOKEN / WHATSAPP_PHONE_ID missing. Run `check` first.")
        return 1
    digits = "".join(ch for ch in number if ch.isdigit())
    body = {"messaging_product": "whatsapp", "to": digits, "type": "template",
            "template": {"name": "hello_world", "language": {"code": "en_US"}}}
    req = urllib.request.Request(f"{GRAPH}/{phone_id}/messages", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("Sent. Meta replied:", r.read().decode()[:200])
        return 0
    except urllib.error.HTTPError as e:
        print(f"Meta rejected it ({e.code}): {e.read().decode('utf-8', 'replace')[:400]}")
        print("While the app is in test mode, the recipient number must be added to the allowed list on the API Setup page.")
        return 1


def cmd_webhook(url):
    import os
    env.load()
    ok, msg = check_webhook(url, os.environ.get("WHATSAPP_VERIFY_TOKEN", ""))
    print(msg)
    return 0 if ok else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["check"]:
        return cmd_check()
    if argv[:1] == ["send"] and len(argv) == 2:
        return cmd_send(argv[1])
    if argv[:1] == ["webhook"] and len(argv) == 2:
        return cmd_webhook(argv[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
