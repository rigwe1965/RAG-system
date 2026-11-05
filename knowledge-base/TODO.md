# TODO: Fill in the Knowledge Base

All files are drafted. Most files are now filled. The remaining `[BRACKETS]` are mainly in `website-design/maintenance.md` (plans, prices), `it-support-rmm/remote-management.md` (tool names), `it-support-rmm/onboarding-security.md`, `ai-agency/client-onboarding.md` (data policy) and `crm/common-user-questions.md`, plus deliberate "no booking link yet" notes. Until a bracket is filled, the assistant should say it doesn't have the detail and escalate.

Find what's left: search the folder for `[`.

> This file is for the owner. Do not load it into the RAG index.

## 1. Fill once, reuse everywhere
- [x] Business name: Faiyke
- [x] Business email info@faiyke.com and website faiyke.com applied everywhere (2026-11-05)
- [ ] Booking link (none yet; files say to arrange a call by phone, WhatsApp, or email)
- [x] Contact email, phone/WhatsApp, hours, address (Dortmund) applied to all files
- [x] Emergency number set to the same phone. Confirm you can actually answer urgent IT calls outside hours; 24/7 cover is marked unconfirmed
- [ ] Website URL, social handles
- [ ] Privacy policy link
- [ ] Owner name, team/contact names
- [ ] **Germany/EU review:** currency: **done, all prices now in € incl. 19% VAT** by keeping the numbers (see note below); decide whether B2B services (IT, AI, CRM, websites) should be quoted net instead; 14-day withdrawal right for online hair orders (see `hair-store/ordering-shipping-returns.md`), GDPR for the chatbot and agents, Impressum/legal notice and privacy policy on the site. Get a lawyer's check.

## 2. Files in priority order
| Done | Priority | File | Brackets | Why |
|---|---|---|---|---|
| [ ] | 1 | `general/contact-escalation.md` | 18 | Handoffs fail without it |
| [ ] | 2 | `business-overview.md` | 18 | Source of truth for who you are |
| [ ] | 3 | `hair-store/ordering-shipping-returns.md` | 33 | Most bracketed; most asked about |
| [ ] | 4 | `hair-store/products-faq.md` | 22 | Prices and specs |
| [ ] | 5 | `it-support-rmm/services-sla.md` | 30 | Assistant can't state an SLA until filled |
| [ ] | 6 | `ai-agency/services-pricing.md` | 18 | Prices |
| [ ] | 7 | `website-design/process-cost-timeline.md` | 24 | Prices |
| [ ] | 8 | `crm/what-we-offer.md` | 15 | Prices and platforms |
| [ ] | 9 | `general/lead-qualification.md` | 8 | Minimums, timeline thresholds |
| [ ] | 9 | `hair-store/care-and-usage.md` | 13 | Confirm tips match your hair |
| [ ] | 9 | `hair-store/sizing-quantity.md` | 9 | Confirm bundle weights and counts |
| [ ] | 9 | `ai-agency/process-timeline.md` | 22 | Timelines |
| [ ] | 9 | `ai-agency/client-onboarding.md` | 16 | Data and privacy answers |
| [ ] | 9 | `website-design/tech-stack.md` | 22 | Platforms you use |
| [ ] | 9 | `website-design/maintenance.md` | 24 | Plans and ownership |
| [ ] | 9 | `it-support-rmm/onboarding-security.md` | 19 | Security baseline, compliance wording |
| [ ] | 9 | `crm/implementation.md` | 17 | Timelines |
| [ ] | 9 | `general/voice-guidelines.md` | 4 | Emoji policy, example ranges |
| [ ] | later | `it-support-rmm/remote-management.md` | 23 | Tool names |
| [ ] | later | `crm/common-user-questions.md` | 21 | Platform-specific steps |

## 3. Claims to confirm before going live
- [ ] Hair: virgin / remy / raw wording, origin, colorability, lifespan
- [ ] Returns policy for altered or installed hair
- [ ] Hair bundle weights (sizing table assumes standard bundles)
- [ ] AI agency: data handling, whether client data trains models, no certifications claimed
- [ ] Website: who owns design, code, and content, and when
- [ ] Website: hacked-site cleanup (in plan or quoted)
- [ ] IT: SLA response and resolution times, after-hours availability
- [ ] IT: what RMM monitoring collects; tools named
- [ ] IT: compliance (HIPAA, PCI, SOC 2). State only what you hold
- [ ] CRM: platforms supported and platform-specific steps

## 4. Reconcile overlaps (new `ai-agency/ai-agent-integrations.md`)
- [x] **Net vs gross (done):** business services are now quoted net, plus VAT (figures = earlier gross ÷ 1.19, rounded). Hair store stays gross (VAT included). Your own agent range stays €150–€600+ and is now labelled "plus VAT"; change it if it was meant to include VAT.
- [ ] **Currency conversion note (earlier step, now superseded for business services):** the proposed prices were USD, roughly net. Converting to euros (about 0.85–0.9 per dollar, my assumption, not a live rate) and adding 19% VAT comes out near 1:1, so I changed `$` to `€` and kept the numbers. Check the real rate and your costs. Your own agent range from the integrations file ($150–$600+) is now shown as €150–€600+ incl. VAT; confirm that is what you intend.
- [x] Pricing: agent row in `services-pricing.md` now uses €150–€600+/month from `ai-agent-integrations.md`. Still open: chatbot, voice, RAG, automation, consulting prices, and the agent setup fee.
- [x] Timelines: `process-timeline.md` now uses the `ai-agent-integrations.md` figures. Still open: RAG, voice, workflow automation rows, the per-stage times, and whether the integration timelines start at kickoff or after onboarding.
- [ ] Platforms: this file lists CRMs (HubSpot, Salesforce, Zoho, Pipedrive, Dynamics 365) and RMM/PSA tools (NinjaOne, ConnectWise, Datto, Autotask, HaloPSA, Syncro). Confirm they match `crm/what-we-offer.md` and `it-support-rmm/remote-management.md`.
- [ ] Confirm you can back up the GDPR / data residency line (now also in `client-onboarding.md`).
- [x] `client-onboarding.md` updated with integration access, guardrails, and security points. Still open: data storage/retention, training use, NDA/DPA, form link, project manager, onboarding time estimate.

- [x] `it-support-rmm/remote-management.md` now has an AI agents with RMM/PSA section. Still open: your own RMM, remote-access, PSA and security tool names, supported OS list, and what monitoring collects.

- [x] `crm/what-we-offer.md` now lists CRM platforms and has an AI agent integration section.
- [x] `crm/what-we-offer.md` approved and live (prices as proposed, net + VAT; 50/50 payments; no license resale; no discounts; platforms you implement: HubSpot, Zoho, Pipedrive, Salesforce, Dynamics 365). The per-platform "best for" lines are general descriptions I wrote; check they match your experience.

- [x] `it-support-rmm/services-sla.md` approved and live: response targets Critical 1 h / High 4 business h / Normal 1 business day / Low 2 business days (no fixed fix times); support Mon–Fri 8:00–18:00, Critical phone line outside hours best effort only; prices Monitoring €5–€12/device, Essential €60–€110/user, Complete €110–€190/user, project €85–€150/hour (net + VAT); 12-month contract then month-to-month, no setup fee. **Make your signed IT contract match this wording.** Still open: on-site support (assistant says "ask the team"), what the Complete plan's security and backup include, a ticket portal, and whether to list endpoint security, backup, network, procurement, vCIO and training as services. (response and resolution times, support hours, after-hours, exclusions, escalation). Only commit to times you can staff. Edit each, delete the "(PROPOSED)" markers and the draft banner, and have your contract match. Not loaded live until then. **Still blocked on you:** plan prices, minimums, contract terms, setup fee. The AI-assisted service desk add-on is already in.

- [~] `it-support-rmm/onboarding-security.md`: added the AI agent security & governance section. Still open: which baseline protections you really provide, tools, onboarding timeline, compliance wording, emergency number.

- [x] `hair-store/ordering-shipping-returns.md` finalized with your choices (worldwide, €4.90 DE / free over €75, 14-day returns, card/PayPal/Klarna/bank transfer) and now live in the index. **Still to do:** have a lawyer check it against German consumer law (Widerrufsbelehrung, Muster-Widerrufsformular, Gewährleistung), and fill the remaining brackets: website URL, carriers, order cutoff time, bank-transfer deadline, custom-wig lead time, lost-package days, exchanges, store credit, wholesale, promos. EU/world shipping prices are "calculated at checkout".
- [x] `hair-store/products-faq.md`: hair type is "100% human hair" only (no virgin/remy/raw/origin claims), and the euro prices (incl. VAT) are approved and live. Textures, lengths (10"–30", bobs from 8"), and colors (natural black 1B, browns, blonde 613) are now live; I read your garbled "1, 2, 3" color answer as all three options, so correct me if wrong. FAQ answers are written (careful, no unconfirmed claims). Lace (HD, transparent, full/360, glueless), closure 4x4/5x5/6x6, frontal 13x4/13x6, wig density 150–250%, and one adjustable cap size are now live (also in `sizing-quantity.md`). **No (PROPOSED) content is left anywhere in the knowledge base.** Bundle weight is 100 g and the assistant says nothing about origin (both final). Still blank: whether wig combs are included. **Facts only you know, currently answered with "ask the team":** installation service, pre-plucked status per wig, lace shades available, photo/video location, wholesale terms. `care-and-usage.md` is now filled with general guidance (wash every 1–2 weeks, heat up to ~180 °C/350 °F, darker coloring is safer, sew-in upkeep ~6–8 weeks); sanity-check these against your supplier's advice. Market notes are in `../market-research.md`.
- [x] Small details filled with my suggested defaults (confirm they are true for you): carriers DHL (DE/EU) and DHL Express or similar (world); order cutoff 14:00; bank-transfer deadline 7 days; custom-wig lead time 7–14 business days; lost-package wait 7 business days; exchanges yes (unused, within 14 days); store credit no; wholesale handled case by case with no minimum; no promo codes; inquiries answered within 1 business day; no minimum project sizes. **Not given, so omitted:** shop URL, founding year, owner name, social handles, whether wigs include combs, a privacy policy link. The assistant says it doesn't have these.
- [x] Timeline estimates finalized with defaults in `ai-agency/process-timeline.md`, `ai-agency/client-onboarding.md` and `crm/implementation.md` (AI: discovery 30–60 min free, proposal 2–5 business days, onboarding ~1 week, testing 3–7 days, launch 1–3 days; RAG 2–4 weeks, voice 3–5, workflow 1–2; CRM: setup 1–3 weeks, integrations 1–3 days each, training 1–2 h per group). They are soft "typically" figures.
- [ ] I chose these delivery estimates myself (DE 2–4, EU 4–8, world 7–14 business days; 1–3 days processing). Confirm them against your carrier.

- [x] `website-design/process-cost-timeline.md` approved and live (prices as proposed, net + VAT; 50/25/25 payments; 2 revision rounds; client owns design, code and content after final payment; copywriting is a separately quoted extra). Still open: the copywriting price, and hosting/domain terms (see `tech-stack.md` and `maintenance.md`).

- [x] **`ai-agency/services-pricing.md` approved and live** (prices approved as proposed, net + VAT; 50% deposit / 50% at launch; month-to-month, 30 days' notice; no discounts). Still open there: data-storage/retention/model-training answers (the assistant says "covered in the agreement"), the post-launch support period.

## 5. Not yet done
- [x] Add a voice-mode section to `general/voice-guidelines.md` (done)
- [ ] Test the assistant with real questions from each business line
- [x] RAG system built in `../rag/` (see `../README.md`). `TODO.md` is excluded from the index.
- [x] Search check with 28 realistic questions (`python -m tests.try_questions`): right file found for 26. Result: the biggest gap is content, not search. 18 of 28 questions land on passages that still have `[placeholders]`, and shipping, returns, SLA, and price answers are hidden until you approve the (PROPOSED) values.
- [ ] Run it with your API key and ask real questions (in English and German). Rebuild with `python -m rag.ingest` after every knowledge-base edit.
- [x] Hand-off built (saved to `handoffs/`, optional email). **Still to do:** set the SMTP variables (see `../README.md`) and send a test hand-off.
- [x] Website chat widget and WhatsApp server built (`../rag/server.py`, `../web/widget.js`). **Still to do:** host the server on a public https address, add the widget to your site, create the Meta WhatsApp Business app and webhook, and test both with real messages.
- [ ] **WhatsApp:** follow `../docs/whatsapp-setup.md` (create the Meta app, fill in `.env`, run `python -m rag.whatsapp_setup check`, test with a tunnel, then host the server and complete Meta business verification). Code, helper commands and guide are ready.
- [ ] **Website chat:** follow `../docs/website-chat-setup.md` (host the server with https, set `ALLOWED_ORIGINS`, paste the script tag into your site, test on phone and PC). The widget is bilingual (EN/DE); code and guide are ready.
- [ ] Your website needs a privacy policy that covers the AI chat, WhatsApp, Anthropic as a processor, and hand-off records (GDPR/Datenschutz), plus an Impressum
