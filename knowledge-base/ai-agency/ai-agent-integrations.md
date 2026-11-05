# AI Agent Integrations – Knowledge Base

## What is an AI Agent vs a Chatbot?
- **Chatbot**: Answers questions from a knowledge base or scripts. Mostly conversational.
- **AI Agent**: Can reason, plan multi-step tasks, call tools/APIs, read/write data in other systems, and take actions (with guardrails).
  Example: "Look up this customer's last order in the CRM, check inventory, create a support ticket in the RMM/PSA, and notify the technician."

We build both. Most client projects start as a strong chatbot and evolve into agents.

---

## Core Integration Architecture (Our Standard Approach)

We use a **governed tool layer** so the AI never has unrestricted access:

1. **AI Agent (Claude / other models)** – Interprets the request and decides which tools to call.
2. **Tool / Integration Layer** – Only approved, narrow actions (via APIs, webhooks, or MCP servers).
3. **Business Systems** – CRM, RMM, website, e-commerce, helpdesk, etc.
4. **Guardrails** – Least-privilege credentials, human approval for high-risk actions, full audit logs, confidence thresholds.

**Preferred modern standard**: Model Context Protocol (MCP).
MCP lets any compatible AI (Claude, ChatGPT, etc.) call your systems through a standardized, secure interface. We build or connect MCP servers for CRM, RMM, PSA, and custom tools.

---

## Integrations We Commonly Deliver

### 1. CRM Integrations (Highest Demand)
Supported platforms: HubSpot, Salesforce, Zoho, Pipedrive, Dynamics 365, custom CRMs.

**What the agent can do**:
- Create / update contacts, leads, deals, tickets
- Look up customer history, order status, previous conversations
- Log full chat transcripts + intent tags
- Trigger workflows (email sequences, task creation, stage changes)
- Qualify leads and book meetings directly into calendars

**Typical first workflows**:
- Website lead capture → CRM with full conversation context
- Support questions that need account data ("Where is my refund?")
- Order status + re-order suggestions (especially useful for the hair store)

**Timeline** (approximate):
- Basic read + lead write: 3–10 days
- Full bidirectional + actions: 2–4 weeks

### 2. Website & E-commerce Integrations
- Embed agent on website (widget or full-page)
- Product catalog search + recommendations (hair length, texture, quantity advice)
- Cart assistance, order status, returns initiation
- Lead qualification forms that feed CRM
- Voice mode on the website (speech-to-text + text-to-speech)

### 3. IT Support / RMM / PSA Integrations (MSP-focused)
Common platforms: NinjaOne, ConnectWise (RMM + PSA), Datto, Autotask, HaloPSA, Syncro, Microsoft 365, etc.

**Agent capabilities**:
- Create / update / close tickets with full context
- Query device health from RMM
- Run approved scripts or stage fixes (with technician approval)
- Gather missing info from the end-user via Voice / Teams / Email agents before a ticket is fully created
- Proactive alerts → structured tickets

**Security emphasis**:
Least-privilege API keys, session logging, human-in-the-loop for any device-changing action, MFA everywhere.

### 4. Helpdesk / Messaging Channels
Zendesk, Intercom, Freshdesk, Gorgias, WhatsApp, Instagram, Facebook Messenger, Slack, Microsoft Teams, email, SMS.

Seamless human handoff with full conversation history.

### 5. Other Common Tools
- Calendar (Google / Outlook) for booking
- Email (Gmail / Microsoft 365)
- Payment / invoicing systems
- Inventory / e-commerce backends
- Documentation systems (IT Glue, Hudu, Notion, Confluence)

---

## How We Implement Integrations (Our Process)

1. **Discovery** – Map current systems, data flows, and desired actions.
2. **Scope & Guardrails** – Define exactly which tools the agent may call and which require human approval.
3. **Authentication** – OAuth, API keys, or MCP with per-user or per-tenant permissions.
4. **Build / Connect** – Native connectors, custom APIs, webhooks, Zapier/Make/n8n, or MCP servers.
5. **Testing** – Shadow mode first (agent suggests, human confirms), then limited autonomy.
6. **Monitoring & Iteration** – Full audit logs, success/failure metrics, continuous improvement of the knowledge base and tools.

**Typical project timeline**:
- Simple FAQ bot + CRM lead capture: 1–2 weeks
- Full agent with 3–5 systems: 3–6 weeks
- Complex multi-agent / high-security MSP setup: 6–10 weeks

---

## Security & Governance Best Practices (What We Always Apply)

- Least privilege – agent gets only the minimum permissions needed
- Human-in-the-loop for irreversible or high-value actions
- Complete audit trail of every tool call
- Data isolation (one customer's data never leaks to another)
- Rate limiting and validation on every write
- Easy kill-switch / feature flags
- Compliance alignment (GDPR, data residency if required)

---

## Common Client Questions & Answers

**Q: Can the AI agent work inside our existing CRM or helpdesk instead of a separate chat window?**
A: Yes. We can embed it or connect via the platform's bot/channel APIs so the conversation stays in the same thread when a human takes over.

**Q: Will the agent hallucinate or invent data?**
A: We design it not to. Answers that need live data come from real system lookups, and the agent is grounded in the knowledge base plus approved tools. No AI system is perfect, which is why we use shadow mode, audit logs, and human approval for high-risk actions.

**Q: How do you stop the agent from accessing the wrong customer's data?**
A: We authenticate the user first and pass only verified identifiers into every API call. Permissions are enforced at the integration layer.

**Q: Can one agent connect to multiple CRMs or systems?**
A: Yes. We use a middleware/orchestration layer or MCP so the agent can route to the correct system.

**Q: Do we need developers on our side?**
A: Usually not. We handle the technical work. You mainly provide access credentials and approve the workflows.

**Q: What happens when the agent doesn't know the answer?**
A: It escalates cleanly to a human with full context and does not make up information.

**Q: Can we start small and expand later?**
A: Strongly recommended. We almost always begin with one high-value workflow (e.g., lead capture or order status) and expand once trust and metrics are proven.

---

## Voice-Enabled Agents
All of the above can run with voice input/output:
- Speech-to-Text (Whisper, ElevenLabs Scribe, browser SpeechRecognition)
- Claude reasoning + tools
- Text-to-Speech (ElevenLabs preferred for quality)
- Barge-in / interruption support
- Available on website, phone, WhatsApp, Teams, etc.

---

## Pricing Guidance (High-Level)
- Setup / integration fee: project-based
- Ongoing: monthly platform + usage or flat retainer
- Typical range for a production agent with 2–4 integrations: €150–€600+/month plus VAT depending on volume and complexity

(Exact quotes after discovery. Route quote requests per `../general/contact-escalation.md`.)

---

**Last updated**: November 2026
Use this document as the single source of truth for all AI agent integration questions.
