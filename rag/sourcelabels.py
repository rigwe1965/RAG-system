"""Friendly names for the knowledge-base files an answer was based on.

The chat page shows "Based on: Ordering, shipping & returns" under an answer, so a customer can see which part of our
information it came from. Only a short title and a service-line key are sent to the browser, never a file path, a
folder layout or any passage text. Titles come from the first heading of each file ("# Hair Store: Care & Usage").
"""
import re

from .ingest import KB_DIR, PROMPT_FILES, SKIP_FILES

LINES = {  # folder -> key the page uses for the colour (hair, ai, web, it, crm) and a readable name
    "hair-store": ("hair", "Hair store"),
    "ai-agency": ("ai", "AI agency"),
    "website-design": ("web", "Website design"),
    "it-support-rmm": ("it", "IT support"),
    "crm": ("crm", "CRM"),
}
KEEP_CAPS = {"AI", "CRM", "RMM", "SLA", "FAQ", "IT", "PSA", "MCP", "GDPR"}
MAX_LABELS = 3
_cache = {}


def _sentence_case(title):
    words = title.split()
    out = []
    for i, w in enumerate(words):
        core = re.sub(r"[^A-Za-z]", "", w)
        out.append(w if (i == 0 or core.upper() in KEEP_CAPS or not core) else w[0].lower() + w[1:])
    return " ".join(out)


def _title_of(rel):
    if rel == "business-overview.md":
        return "About Faiyke"
    try:
        for line in (KB_DIR / rel).read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                title = re.sub(r"\s+[–-]\s+Knowledge Base$", "", title)
                return _sentence_case(title.split(":", 1)[1].strip() if ":" in title else title)
    except OSError:
        pass
    return _sentence_case(rel.rsplit("/", 1)[-1].removesuffix(".md").replace("-", " ").replace("_", " ").title())


def _is_kb_file(rel):
    try:
        path = (KB_DIR / rel).resolve()
        path.relative_to(KB_DIR.resolve())
        return path.is_file()
    except (ValueError, OSError):
        return False


def label(rel):
    """{"line": key, "line_name": text, "title": text} for one knowledge-base file, or None if it is not a customer source."""
    if not isinstance(rel, str) or not rel.endswith(".md") or rel in SKIP_FILES or rel in PROMPT_FILES or ".." in rel:
        return None
    if rel not in _cache:
        if not _is_kb_file(rel):  # only a file that really is in the knowledge base gets a name
            return None
        folder = rel.split("/", 1)[0] if "/" in rel else ""
        key, name = LINES.get(folder, ("general", "Faiyke"))
        _cache[rel] = {"line": key, "line_name": name, "title": _title_of(rel)}
    return dict(_cache[rel])


def labels(files):
    """Labels for the files an answer used, most useful first, at most MAX_LABELS, no duplicate titles."""
    out, seen = [], set()
    for rel in files or ():
        item = label(rel)
        if item and item["title"] not in seen:
            seen.add(item["title"])
            out.append(item)
    return out[:MAX_LABELS]
