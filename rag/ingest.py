"""Build the search index from the knowledge-base folder.

Usage:  python -m rag.ingest
Writes: index/chunks.json
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "knowledge-base"
INDEX_PATH = ROOT / "index" / "chunks.json"

# Loaded into the system prompt on every request, so they are not retrieved.
PROMPT_FILES = [
    "CLAUDE.md",
    "general/voice-guidelines.md",
    "general/contact-escalation.md",
    "general/lead-qualification.md",
]
# Owner-only notes, never shown to the assistant.
SKIP_FILES = {"TODO.md"}

MAX_CHARS = 1400
HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")
# [bracketed text] that is not a markdown link and not a checkbox
PLACEHOLDER = re.compile(r"\[(?!\s*[xX~ ]?\s*\])[^\]\n]{2,}\](?!\()")


def split_paragraphs(text, limit=MAX_CHARS):
    """Split text on blank lines, packing paragraphs up to `limit` characters."""
    parts, current = [], ""
    for para in re.split(r"\n\s*\n", text.strip()):
        if current and len(current) + len(para) + 2 > limit:
            parts.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current.strip():
        parts.append(current.strip())
    return parts


def sections(markdown):
    """Yield (heading_path, body) for each heading section of a markdown file."""
    stack, body, in_fence, seen_h2 = [], [], False, False

    def flush():
        text = "\n".join(body).strip()
        if text:
            yield " > ".join(h for _, h in stack), text

    for line in markdown.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else HEADING.match(line)
        if m:
            yield from flush()
            body.clear()
            level = len(m.group(1))
            if level >= 2:
                seen_h2 = True
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2)))
        else:
            # Owner notes (blockquotes before the first "##") are not customer facts.
            if not seen_h2 and line.startswith(">"):
                continue
            body.append(line)
    yield from flush()


def build_chunks():
    chunks = []
    for path in sorted(KB_DIR.rglob("*.md")):
        rel = path.relative_to(KB_DIR).as_posix()
        if rel in SKIP_FILES or rel in PROMPT_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        n = 0
        for heading, body in sections(text):
            for part in split_paragraphs(body):
                n += 1
                chunks.append(
                    {
                        "id": f"{rel}#{n}",
                        "file": rel,
                        "heading": heading,
                        "text": part,
                        "unapproved": "(PROPOSED" in part,
                        "placeholders": len(PLACEHOLDER.findall(part)),
                    }
                )
    return chunks


def main():
    chunks = build_chunks()
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")

    unapproved = [c for c in chunks if c["unapproved"]]
    with_ph = [c for c in chunks if c["placeholders"]]
    print(f"Indexed {len(chunks)} chunks from {len({c['file'] for c in chunks})} files -> {INDEX_PATH}")
    from . import embed
    embed.build_if_possible(chunks)  # semantic vectors, only if the optional extra and the model are in place
    print(f"  {len(unapproved)} chunks contain (PROPOSED) values: hidden from customers unless --include-drafts")
    print(f"  {len(with_ph)} chunks still contain [placeholders]: flagged to the model")
    by_file = {}
    for c in unapproved:
        by_file[c["file"]] = by_file.get(c["file"], 0) + 1
    for f, n in sorted(by_file.items()):
        print(f"    {f}: {n} unapproved")


if __name__ == "__main__":
    main()
