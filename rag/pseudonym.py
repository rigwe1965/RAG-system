"""Keyed hashes for identifiers that must not be reversible from a copy of the data.

A plain SHA-256 of a WhatsApp number can be undone by trying every possible number (about 10^10). A keyed hash
(HMAC-SHA256) cannot, unless the attacker also has the key. The key is kept away from the data folders:

    PRIVACY_HASH_KEY   in .env (at least 32 characters), or else
    .privacy_key       a file in the project folder, made on first use with a random value (mode 600).
                       PRIVACY_KEY_FILE changes its location.

Without either (for example a read-only folder) a random key is made for this run only and a warning is printed:
chats then do not carry on after a restart, but nothing breaks. Never put the key in git or next to sessions/.
"""
import hashlib
import hmac
import os
import secrets
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_lock = threading.Lock()
_cache = {}


def _key_file():
    return Path(os.environ.get("PRIVACY_KEY_FILE", ROOT / ".privacy_key"))


def _load():
    raw = os.environ.get("PRIVACY_HASH_KEY", "").strip()
    if len(raw) >= 32:
        return raw.encode("utf-8")
    path = _key_file()
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if len(value) >= 32:
                return value.encode("utf-8")
        value = secrets.token_hex(32)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value + "\n")
        return value.encode("utf-8")
    except FileExistsError:  # another process made it a moment ago (or the file is there but too short to trust)
        value = path.read_text(encoding="utf-8").strip()
        if len(value) >= 32:
            return value.encode("utf-8")
        print("[privacy] .privacy_key is too short; using a temporary key. Delete the file to make a new one.", file=sys.stderr)
        return secrets.token_hex(32).encode("utf-8")
    except OSError as e:
        print(f"[privacy] cannot keep a hash key ({type(e).__name__}); using a temporary one. "
              "Set PRIVACY_HASH_KEY in .env.", file=sys.stderr)
        return secrets.token_hex(32).encode("utf-8")


def _key():
    with _lock:
        k = (os.environ.get("PRIVACY_HASH_KEY"), str(_key_file()))
        if k not in _cache:
            _cache.clear()
            _cache[k] = _load()
        return _cache[k]


def keyed(prefix, value, length=64):
    """HMAC-SHA256 of `prefix:value`, as hex, cut to `length` characters."""
    mac = hmac.new(_key(), f"{prefix}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()
    return mac[:length]


def legacy(prefix, value, length=64):
    """The old unkeyed hash, kept only so records written before the upgrade can still be found and erased."""
    return hashlib.sha256(f"{prefix}:{value}".encode("utf-8")).hexdigest()[:length]
