# AI Agency: Process & Timeline

> Timelines are estimates, never guarantees. Say "typically".

## How a project works

### 1. Discovery call
Free conversation to understand goals, current processes, tools, and success measures.
- **Output:** summary of the problem and recommended approach.
- **Time:** typically 30–60 minutes

### 2. Proposal & agreement
We send a scope, timeline, price, and terms.
- **Output:** signed proposal and 50% deposit.
- **Time:** typically 2–5 business days

### 3. Onboarding & setup
Collect access, content, and decisions. See `client-onboarding.md`.
- **Time:** typically about 1 week

### 4. Build
We build the solution: configure the assistant or automation, connect tools, load content, and write the conversation flow.

For AI agents that connect to your systems (CRM, RMM/PSA, website, helpdesk), the build also includes:
- **Scope & guardrails:** define exactly which tools the agent may call and which actions need human approval.
- **Authentication:** OAuth, API keys, or MCP with per-user or per-tenant permissions, using least-privilege access.
- **Build / connect:** native connectors, custom APIs, webhooks, Zapier/Make/n8n, or MCP servers.

Details are in `ai-agent-integrations.md`.
- **Time:** see table below

### 5. Testing & review
We test internally, then with your team. You review and give feedback. We refine.

For agents, we start in **shadow mode**: the agent suggests, a human confirms. Autonomy is then widened in limited steps, with full audit logs of every tool call.
- **Time:** typically 3–7 days

### 6. Launch
Go live, often in stages (soft launch, then full). Staff are briefed.
- **Time:** typically 1–3 days

### 7. Support & optimization
We monitor performance, review conversations and tool calls, track success and failure metrics, fix issues, and improve the knowledge base and tools over time.
- **Time:** ongoing, on a monthly plan

## Start with one workflow
We almost always begin with one high-value workflow, such as lead capture into the CRM or order status. Once it works and the metrics prove it, we expand to more workflows and systems. Most projects start as a strong chatbot and grow into an agent.

## Typical timelines
| Project | Estimated time |
|---|---|
| Simple FAQ bot + CRM lead capture | 1–2 weeks |
| CRM integration: basic read + lead write | 3–10 days |
| CRM integration: full two-way with actions | 2–4 weeks |
| Full agent with 3–5 systems | 3–6 weeks |
| Complex multi-agent / high-security MSP setup | 6–10 weeks |
| Knowledge-base assistant (RAG) | 2–4 weeks |
| Voice agent | 3–5 weeks |
| Workflow automation (per workflow) | 1–2 weeks |
| Custom AI solution | Scoped per project |

The first five rows come from `ai-agent-integrations.md`. They are estimates, and it's not specified whether they count from kickoff or from the end of onboarding. Say "typically" and confirm on a discovery call.

**Overall:** most projects land between 1 and 10 weeks, depending on the number of systems and the security requirements.

## What can slow things down
- Late access to accounts, tools, or content
- Slow feedback or approvals
- Unclear or changing requirements
- Complex integrations
- Poor or missing source content

## What we need from you
- A main contact who can make decisions
- Access to relevant tools and systems
- Content: FAQs, policies, product info, past conversations
- Timely feedback on tests
- Clear goals and success metrics

## What you get
- A working solution tested against real questions
- Documentation and a handover session
- A handover session so your team knows how to use and review it
- A post-launch support period, agreed in the proposal

## After launch
- **Monitoring:** we track unanswered questions, hand-offs to people, tool calls, user feedback, and success and failure rates
- **Updates:** adding content and fixing gaps
- **Reporting:** a monthly summary on a monthly plan
- **Changes outside scope:** quoted separately.

## Common questions
**How long until we can go live?**
Give the estimate for their project type from the table. Add that it depends on how quickly content and access arrive. Offer a discovery call for a firmer timeline.

**Do I need to be technical?**
No. We handle the technical work. We need you for business knowledge and feedback.

**Can we start small?**
Yes, and we strongly recommend it. Start with one high-value workflow, prove it, then expand.

**Will the agent act on its own right away?**
No. We begin in shadow mode where the agent suggests and a person confirms. Risky or irreversible actions keep human approval even after launch.

**Can you change it after launch?**
Yes. Monitoring, fixes, content updates, and small improvements are covered on a monthly plan; larger changes are quoted.

## Next step
Offer a discovery call: [no booking link yet: arrange a call by phone, WhatsApp, or email]. For custom timelines, escalate per `../general/contact-escalation.md`.
