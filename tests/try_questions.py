"""Check what the assistant can find for realistic customer questions (no API key needed).

    python -m tests.try_questions

For each question it shows the best passages in customer-safe mode (what a customer's
assistant would see) and flags problems:
  NO HIT   nothing relevant is retrievable, so the assistant will say it doesn't know
  DRAFT    the only good answer is hidden because it is still marked (PROPOSED)
  OFF      the expected file is not in the top results
  GAPS     the best passage still has [placeholders]
German questions use the English query that Claude's rewrite step would produce.
"""
import sys

from rag.ingest import build_chunks
from rag.retrieve import Index

# (question as the customer types it, English search query, file that should answer it)
CASES = [
    ("What are your opening hours?", "opening hours", "business-overview.md"),
    ("Wo seid ihr eigentlich? Kann ich vorbeikommen?", "address location visit", "business-overview.md"),
    ("How do I reach you on WhatsApp?", "contact phone whatsapp", "business-overview.md"),
    ("Do you sell 100% human hair?", "human hair virgin remy", "hair-store/products-faq.md"),
    ("How many bundles do I need for a full 22 inch body wave?", "how many bundles 22 inch full", "hair-store/sizing-quantity.md"),
    ("What's the difference between a closure and a frontal?", "closure frontal difference", "hair-store/products-faq.md"),
    ("How do I wash my wig?", "wash wig care", "hair-store/care-and-usage.md"),
    ("Kann ich die Haare färben?", "can hair be colored bleached", "hair-store/care-and-usage.md"),
    ("How long does shipping take?", "shipping time delivery", "hair-store/ordering-shipping-returns.md"),
    ("Can I return a wig I wore once?", "return worn wig", "hair-store/ordering-shipping-returns.md"),
    ("Mein Paket ist beschädigt angekommen", "damaged item received", "hair-store/ordering-shipping-returns.md"),
    ("How much does a business website cost?", "website price cost", "website-design/process-cost-timeline.md"),
    ("How long to build a website with an online shop?", "e-commerce website timeline", "website-design/process-cost-timeline.md"),
    ("Do you use WordPress or Shopify?", "wordpress shopify platform", "website-design/tech-stack.md"),
    ("Who updates my website after launch?", "website maintenance plan", "website-design/maintenance.md"),
    ("Can you build a chatbot for our WhatsApp?", "chatbot whatsapp", "ai-agency/services-pricing.md"),
    ("What does an AI agent cost per month?", "ai agent monthly price", "ai-agency/services-pricing.md"),
    ("Can the AI create tickets in ConnectWise?", "ai agent create tickets connectwise PSA", "ai-agency/ai-agent-integrations.md"),
    ("How do you stop the AI seeing other customers' data?", "ai agent wrong customer data isolation", "ai-agency/ai-agent-integrations.md"),
    ("What do you need from us to get started with the AI project?", "client onboarding what we need", "ai-agency/client-onboarding.md"),
    ("How fast do you respond to an IT outage?", "response time critical outage SLA", "it-support-rmm/services-sla.md"),
    ("What does monitored IT support cost per user?", "managed IT price per user", "it-support-rmm/services-sla.md"),
    ("Do you install software on all our laptops?", "RMM agent install devices", "it-support-rmm/remote-management.md"),
    ("Are you HIPAA compliant?", "HIPAA compliance", "it-support-rmm/onboarding-security.md"),
    ("Which CRM should we use?", "which CRM best platform", "crm/what-we-offer.md"),
    ("Can you move our contacts from Excel into HubSpot?", "migrate data spreadsheet CRM", "crm/implementation.md"),
    ("I can't log in to my CRM", "cannot log in password reset", "crm/common-user-questions.md"),
    ("Can I speak to a real person?", "speak to human contact", "business-overview.md"),
    ("Do you give discounts for students?", "student discount", None),  # should NOT be answerable
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    index = Index(build_chunks())
    counts = {"ok": 0, "NO HIT": 0, "DRAFT": 0, "OFF": 0, "GAPS": 0}
    for question, query, expected in CASES:
        safe = index.search(query, k=3)
        allhits = index.search(query, k=3, include_drafts=True)
        flags = []
        if expected is None:
            flags.append("ok (should be unanswerable)" if not safe or safe[0][0] < 6 else "OFF (answering something unknown?)")
        else:
            if not safe:
                flags.append("NO HIT" + (" (DRAFT hides it)" if allhits and allhits[0][1]["file"] == expected else ""))
            elif expected not in [c["file"] for _, c in safe]:
                flags.append("DRAFT" if any(c["file"] == expected for _, c in allhits) else "OFF")
            if safe and safe[0][1]["placeholders"]:
                flags.append("GAPS")
        flag = ", ".join(flags) or "ok"
        key = "NO HIT" if flag.startswith("NO HIT") else "DRAFT" if flag.startswith("DRAFT") else "OFF" if "OFF" in flag else "GAPS" if "GAPS" in flag else "ok"
        counts[key] = counts.get(key, 0) + 1
        print(f"\n[{flag}] {question}\n   query: {query}   expected: {expected}")
        for score, c in safe:
            mark = "*" if c["file"] == expected else " "
            print(f"   {mark} {score:5.1f} {c['file']} > {c['heading'].split(' > ')[-1][:45]}"
                  f"{'  [gaps]' if c['placeholders'] else ''}")
    print("\nSummary:", counts)


if __name__ == "__main__":
    main()
