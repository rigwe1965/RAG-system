"""BM25 keyword retrieval over the chunk index (no external dependencies)."""
import json
import math
import re
from collections import Counter

from .ingest import INDEX_PATH

STOP = set(
    "a an the and or but of to in on at for from with by is are was were be been am it its this that these those "
    "do does did can could would should will we you i me my our your they them their what which who how when where "
    "why if so as not no yes about any some there here have has had get got also please".split()
)
WORD = re.compile(r"[a-zA-Z0-9äöüÄÖÜß€]+")


def stem(word):
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text):
    return [stem(w) for w in (w.lower() for w in WORD.findall(text)) if w not in STOP]


# Words customers use interchangeably. Applied to the query only.
SYNONYMS = [
    "cost price pricing fee rate charge expensive cheap budget quote",
    "hour open opening closing schedule available availability",
    "contact reach email phone address location",
    "ship shipping deliver delivery carrier tracking",
    "return refund exchange withdraw cancel",
    "timeline duration turnaround",
    "inch inches size sizing",
    "migrate migration import transfer move moving",
    "install installation setup implementation implement",
]
SYN_GROUPS = [set(stem(w) for w in g.split()) for g in SYNONYMS]


# Words that tell us which business line a question is about (matched on the raw query words).
FOLDER_HINTS = {
    "crm/": {"crm", "hubspot", "zoho", "pipedrive", "salesforce", "dynamics", "pipeline", "deals"},
    "website-design/": {"website", "websites", "webshop", "wordpress", "shopify", "webflow", "seo", "landing", "domain", "hosting"},
    "hair-store/": {"hair", "wig", "wigs", "bundle", "bundles", "closure", "frontal", "lace", "extensions"},
    "ai-agency/": {"ai", "chatbot", "chatbots", "agent", "agents", "voice", "automation", "mcp", "llm"},
    "it-support-rmm/": {"rmm", "msp", "helpdesk", "outage", "ransomware", "patching", "sla", "endpoint", "laptops"},
}
FOLDER_BOOST = 1.35


def hinted_folders(query, hints_by_folder=None):
    """Folders a question seems to be about. `hints_by_folder` defaults to the Faiyke business lines above."""
    table = FOLDER_HINTS if hints_by_folder is None else hints_by_folder
    words = set(WORD.findall(query.lower()))
    return {folder for folder, hints in table.items() if words & hints}


def expand(terms, weight=0.4):
    """Query terms with weight 1, plus synonyms with a lower weight."""
    out = {t: 1.0 for t in terms}
    for t in list(out):
        for g in SYN_GROUPS:
            if t in g:
                for s in g:
                    out.setdefault(s, weight)
    return out


RRF_K = 60        # how quickly lower ranks count less when the two rankings are merged
POOL = 20         # how many results from each ranking are merged
# Chosen from measurements on the real knowledge base (see tests/test_pending.py): questions that are not about a
# pending page never had a draft match above 0.43 and always trailed the best approved passage by 0.17 or more.
PENDING_SIM = 0.40     # a hidden draft must match the question at least this well (by meaning) ...
PENDING_MARGIN = 0.0   # ... and beat the best approved passage by more than this, to count as "the answer is pending"


class Index:
    def __init__(self, chunks, k1=1.5, b=0.75, vectors=None, folder_hints=None):
        """`vectors` is optional (see embed.py). Without it this is plain keyword search.
        `folder_hints` replaces the built-in Faiyke folder hints ({} switches the boost off)."""
        self.chunks, self.k1, self.b, self.vectors = chunks, k1, b, vectors
        self.folder_hints = FOLDER_HINTS if folder_hints is None else folder_hints
        # The section's own heading counts three times; the page title and file name once.
        def doc_text(c):
            last = c["heading"].split(" > ")[-1]
            return f"{c['file']} {c['heading']} {last} {last} {c['text']}"

        self.docs = [Counter(tokenize(doc_text(c))) for c in chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    @classmethod
    def load(cls, path=INDEX_PATH, use_vectors=True):
        chunks = json.loads(path.read_text(encoding="utf-8"))
        vectors = None
        if use_vectors:
            from . import embed  # optional extra; returns None when it is not installed or not usable
            vectors = embed.load_vectors(chunks)
        return cls(chunks, vectors=vectors)

    def search(self, query, k=6, include_drafts=False, min_score=1.0):
        """Return up to k (score, chunk) pairs, best first.

        Keyword search (BM25) always runs. If semantic vectors are available, chunks whose meaning is
        close to the question are merged in (reciprocal rank fusion), so a question worded very
        differently from the text, or written in German, can still find the right passage.
        """
        keyword = self.keyword_search(query, include_drafts, min_score)
        if self.vectors is None:
            return keyword[:k]
        sims = self.vectors.scores(query)
        if sims is None:
            return keyword[:k]
        from .embed import MIN_SIM
        near = [(float(s), i) for i, s in enumerate(sims)
                if s >= MIN_SIM and (include_drafts or not self.chunks[i]["unapproved"])]  # drafts stay hidden
        if not near:
            return keyword[:k]
        near.sort(key=lambda t: t[0], reverse=True)
        fused, by_id = {}, {}
        for rank, (_, chunk) in enumerate(keyword[:POOL]):
            fused[chunk["id"]] = fused.get(chunk["id"], 0.0) + 1.0 / (RRF_K + rank + 1)
            by_id[chunk["id"]] = chunk
        for rank, (_, i) in enumerate(near[:POOL]):
            c = self.chunks[i]
            fused[c["id"]] = fused.get(c["id"], 0.0) + 1.0 / (RRF_K + rank + 1)
            by_id[c["id"]] = c
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [(score * 100, by_id[cid]) for cid, score in ranked]

    def semantic_draft_wins(self, query):
        """True when, by meaning, a hidden draft (PROPOSED) chunk fits the question clearly better than any
        approved chunk. Compares similarities, which stay comparable (unlike the merged search scores).
        Needs both a solid match (PENDING_SIM) and a lead over the approved text (PENDING_MARGIN), so an approved
        passage on the same topic keeps the assistant answering."""
        if self.vectors is None:
            return False
        sims = self.vectors.scores(query)
        if sims is None:
            return False
        drafts = [float(s) for s, c in zip(sims, self.chunks) if c["unapproved"]]
        approved = [float(s) for s, c in zip(sims, self.chunks) if not c["unapproved"]]
        if not drafts:
            return False
        best_draft, best_approved = max(drafts), max(approved, default=-1.0)
        return best_draft >= PENDING_SIM and best_draft - best_approved > PENDING_MARGIN

    def keyword_search(self, query, include_drafts=False, min_score=1.0):
        """All keyword (BM25) matches, best first."""
        terms = expand(tokenize(query))
        folders = hinted_folders(query, self.folder_hints)
        scored = []
        for chunk, doc, length in zip(self.chunks, self.docs, self.lengths):
            if chunk["unapproved"] and not include_drafts:
                continue
            score = 0.0
            for t, w in terms.items():
                f = doc.get(t, 0)
                if f:
                    norm = f + self.k1 * (1 - self.b + self.b * length / self.avg_len)
                    score += w * self.idf.get(t, 0) * f * (self.k1 + 1) / norm
            if score and any(chunk["file"].startswith(f) for f in folders):
                score *= FOLDER_BOOST
            if score >= min_score:
                scored.append((score, chunk))
        scored.sort(key=lambda s: s[0], reverse=True)
        return scored
