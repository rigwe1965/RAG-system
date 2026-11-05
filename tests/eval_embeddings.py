"""Does semantic search help, and where should the similarity cutoff be?   python -m tests.eval_embeddings

Needs the optional extra and a built vector index (python -m rag.embed download, then python -m rag.ingest).
Questions are worded differently from the knowledge base on purpose, half of them in German.
"""
import json
import sys

from rag import embed
from rag.ingest import INDEX_PATH
from rag.retrieve import Index

# question -> files where a good answer lives (any one of them counts)
ASK = [
    ("how do I get my money back", {"hair-store/ordering-shipping-returns.md"}),
    ("my package hasn't arrived", {"hair-store/ordering-shipping-returns.md"}),
    ("how do I keep my hair from tangling", {"hair-store/care-and-usage.md"}),
    ("how many packs for a full head", {"hair-store/sizing-quantity.md"}),
    ("what if my computers get hacked", {"it-support-rmm/onboarding-security.md", "it-support-rmm/services-sla.md", "it-support-rmm/remote-management.md"}),
    ("can you build me an online shop", {"website-design/tech-stack.md", "website-design/process-cost-timeline.md"}),
    ("how long until my site goes live", {"website-design/process-cost-timeline.md"}),
    ("will the bot talk to our customer database", {"ai-agency/ai-agent-integrations.md"}),
    ("we want to move from spreadsheets to something that tracks clients", {"crm/what-we-offer.md", "crm/implementation.md", "crm/common-user-questions.md"}),
    ("who looks after my site after launch", {"website-design/maintenance.md"}),
    ("do you ship to America", {"hair-store/ordering-shipping-returns.md"}),
    ("Wie viel kostet ein Chatbot für meine Firma", {"ai-agency/services-pricing.md"}),
    ("Was passiert wenn mein Server ausfällt", {"it-support-rmm/services-sla.md", "it-support-rmm/remote-management.md"}),
    ("Wie pflege ich meine Echthaar-Perücke", {"hair-store/care-and-usage.md"}),
    ("Kann ich meine Bestellung zurückschicken", {"hair-store/ordering-shipping-returns.md"}),
    ("Wie lange dauert die Einführung eines CRM", {"crm/implementation.md", "crm/what-we-offer.md"}),
    ("Wie viele Bundles brauche ich für 24 Zoll", {"hair-store/sizing-quantity.md"}),
    ("Wann habt ihr geöffnet", {"business-overview.md", "it-support-rmm/services-sla.md"}),
    ("Welche Systeme kann der KI-Agent anbinden", {"ai-agency/ai-agent-integrations.md"}),
    ("Was kostet eine Webseite", {"website-design/process-cost-timeline.md"}),
]
OFF = [
    "what's the capital of France", "write me a poem about autumn", "what's the weather tomorrow",
    "xqzv plorb wumble", "who won the football match", "how to bake sourdough bread",
    "Wie wird das Wetter morgen", "tell me a joke", "explain quantum physics", "Wer ist der Bundeskanzler",
]


def main():
    chunks = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    vectors = embed.load_vectors(chunks)
    if vectors is None:
        sys.exit("No usable vector index. Run: python -m rag.embed download && python -m rag.ingest")
    plain, hybrid = Index(chunks), Index(chunks, vectors=vectors)

    def hit(index, q, want, k=3):
        return any(c["file"] in want for _, c in index.search(q, k=k))

    base = sum(hit(plain, q, w) for q, w in ASK)
    print(f"{len(ASK)} paraphrased questions. Right file in the top 3:")
    print(f"  keyword only: {base}/{len(ASK)}")
    top_off = [float(vectors.scores(q).max()) for q in OFF]
    for cut in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
        embed.MIN_SIM = cut
        h = sum(hit(hybrid, q, w) for q, w in ASK)
        leaks = sum(1 for s in top_off if s >= cut)
        print(f"  hybrid, cutoff {cut:.2f}: {h}/{len(ASK)}   off-topic questions that pass the cutoff: {leaks}/{len(OFF)}")
    print("\nHighest similarity of each off-topic question:")
    for q, s in sorted(zip(OFF, top_off), key=lambda t: -t[1]):
        print(f"  {s:.2f}  {q}")
    print("\nQuestions the keyword search misses (top 3):")
    for q, w in ASK:
        if not hit(plain, q, w):
            print("  -", q)


if __name__ == "__main__":
    main()
