"""Who is really on the other end of a connection.

Behind a reverse proxy (Caddy) every connection comes from the proxy's own address, so rate limits and login
lockouts would treat all visitors as one person. The proxy puts the visitor's address in `X-Forwarded-For`, but
anyone can send that header themselves, so it is believed only when the connection comes from a trusted proxy,
and then only the part the proxy itself added (read from the right, skipping trusted proxies).

    TRUSTED_PROXIES   comma list of proxy addresses or networks (default: 127.0.0.1,::1, the proxy on the same
                      server). Set it to "none" if nothing sits in front of the server.
"""
import ipaddress
import os

DEFAULT_TRUSTED = "127.0.0.1,::1"


def _parse(value):
    try:
        return ipaddress.ip_address(value.strip().strip("[]"))
    except ValueError:
        return None


def trusted_networks(raw=None):
    raw = os.environ.get("TRUSTED_PROXIES", DEFAULT_TRUSTED) if raw is None else raw
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part or part.lower() == "none":
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue  # a typo means "not trusted", which is the safe direction
    return nets


def _is_trusted(addr, nets):
    return addr is not None and any(addr in n for n in nets if n.version == addr.version)


def client_ip(peer, forwarded_for, nets=None):
    """The visitor's address as text. `peer` is the address that connected, `forwarded_for` the header (or "")."""
    nets = trusted_networks() if nets is None else nets
    peer_addr = _parse(peer or "")
    if not _is_trusted(peer_addr, nets) or not forwarded_for:
        return peer or "unknown"
    for part in reversed([p for p in forwarded_for.split(",") if p.strip()]):
        addr = _parse(part)
        if addr is None:
            return peer  # a malformed header is not believed at all
        if not _is_trusted(addr, nets):
            return str(addr)
    return peer


def host_allowed(header, raw=None):
    """True if the Host header names one of the sites in ALLOWED_HOSTS (comma list of names, ports ignored).
    Empty list: no check. Used for /admin so a web page cannot reach it under a name of its own (DNS rebinding)."""
    raw = os.environ.get("ALLOWED_HOSTS", "") if raw is None else raw
    names = {n.strip().lower() for n in raw.split(",") if n.strip()}
    if not names:
        return True
    host = (header or "").strip().lower()
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host in names


def allowed(ip, raw=None):
    """True if `ip` is inside the comma list in `raw` (default: ADMIN_ALLOWED_IPS). An empty list allows everyone."""
    raw = os.environ.get("ADMIN_ALLOWED_IPS", "") if raw is None else raw
    if not raw.strip():
        return True  # no list set: no restriction
    # A list that is set but has no valid entry (a typo) allows nobody: failing closed is the safe direction.
    return _is_trusted(_parse(ip or ""), trusted_networks(raw))
