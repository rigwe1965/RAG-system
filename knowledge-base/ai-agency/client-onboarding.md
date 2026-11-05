# AI Agency: Client Onboarding

What happens after a client signs. Used to answer "what do you need from me?" and to set expectations.

> Items in [BRACKETS] are for the owner to fill in.

## Onboarding steps
1. **Kickoff call** typically 30–60 minutes: confirm goals, scope, timeline, contacts, and success measures.
2. **Intake form / checklist:** the client completes [FORM LINK].
3. **Access & content handover:** the client shares what we need (see below).
4. **Configuration plan:** we confirm the plan, tone, escalation rules, and integrations.
5. **Build begins.** See `process-timeline.md`.

## What we need from the client

### People
- Primary contact with decision-making authority
- Subject-matter expert(s) for review
- Technical contact (for access, website, DNS, etc.), if relevant

### Content
- FAQs, policies, price lists, product or service information
- Brand voice, tone, and example replies
- Past customer conversations, tickets, or emails (anonymized if needed)
- Opening hours, contact details, and booking links
- Things the assistant should **never** say or do

### Access (as needed)
- Website or CMS access, or someone who can add a code snippet
- CRM, helpdesk, calendar, or e-commerce accounts
- Messaging channel accounts (WhatsApp, Instagram, Facebook, etc.)
- Phone number setup (for voice agents)
- API keys or integration permissions

> **Security:** Don't share passwords in chat or email. We use [secure method, e.g. shared vault, role-based invites]. Give the minimum access needed.

**For AI agents that connect to your systems** (CRM, RMM/PSA, helpdesk, e-commerce, calendar, email):
- Authentication is by OAuth, API keys, or MCP, with per-user or per-tenant permissions.
- Credentials follow **least privilege**: the agent gets only the permissions it needs, and nothing more.
- For IT/MSP setups, use MFA everywhere. Any action that changes a device needs technician approval.
- You mainly provide access credentials and approve the workflows. You usually don't need developers on your side.

### Decisions
- **Starting workflow:** pick one high-value workflow to begin with (for example lead capture into the CRM, or order status). We expand after it's proven.
- **Tool scope and guardrails:** exactly which actions the agent may take, and which need human approval (anything irreversible or high-value)
- **User verification:** how the agent confirms who it's talking to before it looks up account data
- Escalation rules: when the assistant hands off, and to whom
- Handoff channel: email, phone, CRM task, Slack, etc.
- Business hours and after-hours behavior
- Languages
- Compliance or legal wording needed

## Our responsibilities
- Project manager: [NAME / ROLE]
- Weekly or regular updates: [frequency and channel]
- A written scope and plan, including which tools the agent can call
- Testing and quality checks before launch, starting in shadow mode (the agent suggests, a human confirms)
- Secure handling of client data
- Monitoring after launch: audit logs of every tool call and success/failure metrics

## Data & privacy
- Security measures we always apply to agents: least privilege, human-in-the-loop for irreversible or high-value actions, a complete audit trail of tool calls, rate limiting and validation on every write, and a kill-switch / feature flags.
- **Data isolation:** one customer's data is never exposed to another. Permissions are enforced at the integration layer, and only verified identifiers are passed into API calls.
- **Compliance:** we align with GDPR and data residency requirements where needed. [Confirm exactly what you can state before quoting this to clients.]
- [How client data is stored and who can access it]
- [Whether data is used to train AI models, e.g. "no"]
- [Data retention and deletion]
- [NDA / data processing agreement available on request]
- Don't claim certifications we don't hold.

## Training & handover
- Walkthrough of how it works and how to review conversations
- Guide on how to add or update content: [format]
- How to reach support: info@faiyke.com · +49 176 41565516 [ticket portal, if any]

## Success measures
Agree on 2–3 measurable goals at kickoff, e.g.:
- Share of questions answered without human help
- Response time
- Leads or bookings captured
- Hours saved per week

## Common questions
**What do I need to prepare?**
Share the content list and access list above. Offer the checklist: [LINK].

**How much of my time will this take?**
typically about 2–4 hours in total across kickoff, content handover, and review sessions.

**Is my customer data safe?**
Use the data and privacy section. Stress least privilege, human approval for risky actions, audit logs, and data isolation. If specifics aren't listed, escalate.

**Do we need developers on our side?**
Usually not. We handle the technical work. You provide access credentials and approve the workflows.

**How do you stop the agent from seeing the wrong customer's data?**
We authenticate the user first and pass only verified identifiers into every API call. Permissions are enforced at the integration layer.

**Where do we start?**
With one high-value workflow. We prove it, then expand.

**What if I don't have documentation?**
We can help draft FAQs from your website, emails, or a short interview. We can help; larger drafting work may be quoted separately.

## Next step
Send the onboarding checklist [LINK] or book a kickoff call [no booking link yet: arrange a call by phone, WhatsApp, or email]. Questions about contracts or security reviews go to a human per `../general/contact-escalation.md`.
