# IT Support & RMM: Services & SLA

> Owner-approved service levels, hours, prices and contract terms (November 2026). All prices are in euros and **net: 19% German VAT is added on top**. Response times are targets, not guarantees; the signed contract is what applies. The assistant must never invent SLAs, response times, or uptime figures. Anything not listed here goes to a human.

## What we do
We keep small and mid-sized businesses running with managed IT support: help desk, proactive monitoring, security, and strategic guidance, for a predictable monthly fee.

## Services
| Service | What it covers |
|---|---|
| Help desk | Remote support for staff by phone, WhatsApp, or email |
| Remote monitoring & management (RMM) | Software on devices that monitors health, applies patches, and fixes issues proactively. See `remote-management.md` |
| Patch & update management | OS and software updates on a schedule |
| Email & Microsoft 365 / Google Workspace support | Accounts, licenses, migrations, security |
| User onboarding/offboarding | Accounts, devices, access |
| AI-assisted service desk | An AI agent connected to your RMM/PSA that creates structured tickets, queries device health, and gathers missing details from users by voice, Teams, or email. Device-changing actions need technician approval. See `remote-management.md` and `../ai-agency/ai-agent-integrations.md` |

**Other services we can discuss:** endpoint security, backup and recovery, network and Wi-Fi, hardware and software procurement, IT planning (vCIO), and security awareness training. Scope and price are agreed per client. Don't promise details; offer to ask the team.

## Plans & pricing
All prices are net, plus 19% VAT.

| Plan | Best for | Includes | Price |
|---|---|---|---|
| Monitoring only | Teams with in-house IT | RMM, patching, alerts | €5–€12 per device/month |
| Essential | Small businesses | Monitoring plus help desk during business hours | €60–€110 per user/month |
| Complete | Growing businesses | Essential plus the security and backup services agreed in the contract | €110–€190 per user/month |
| Project work | One-off needs | Migrations, setups, upgrades | €85–€150 per hour |

- **Contract:** 12 months, then month-to-month with 30 days' notice.
- **Setup/onboarding fee:** none.
- **Minimums:** none are stated. Don't quote a minimum; a final quote follows an assessment.
- **Billed extra:** hardware, software licenses, and project work outside the plan (at the hourly rate).
- **Discounts:** none. The assistant must not offer or promise any.
- **Quotes:** all ranges are a guide. A final quote follows discovery or an IT assessment.

### AI-assisted service desk (add-on)
- **Price:** priced as an AI agent. A production agent with 2–4 integrations is typically €150–€600+/month plus VAT depending on volume and complexity, plus a project-based setup fee. Exact quotes come after discovery. See `../ai-agency/services-pricing.md`.
- **Timeline:** complex or high-security MSP setups typically take 6–10 weeks.
- **How it runs:** least-privilege access, technician approval for any device-changing action, MFA everywhere, full audit logs. We start with one workflow and a shadow-mode period before widening autonomy.
- **SLA:** the AI agent does not change the service levels below. Human technicians remain responsible for resolution.

## Service levels (SLA)
Response means a technician has acknowledged the ticket and started work.

| Priority | Example | Response target | Resolution |
|---|---|---|---|
| Critical | Business-wide outage, ransomware or suspected breach, server down | 1 hour | Work continues until service is restored; best effort |
| High | A major system is down, or several users or a key user can't work | 4 business hours | No fixed time; we keep you updated |
| Normal | Single-user issue with a workaround | 1 business day | No fixed time; we keep you updated |
| Low | Requests, questions, new-user setup, planned work | 2 business days | As scheduled |

**How the SLA works**
- **Response** is not the same as resolution. We give response targets, not fixed fix times. Hardware failures, vendor outages, and waiting on the client or a third party can extend how long a fix takes.
- Response times count within **support hours**.
- Priority is set by us based on business impact and may be raised or lowered as we learn more.
- Excluded: issues in systems or devices not covered by the plan, outages of third-party services, and problems caused by changes made without our knowledge.
- All times are targets. What the signed contract says is what applies.

**Support hours:** Monday to Friday 8:00–18:00, Germany time. There is no IT support on Saturdays or Sundays.
**Outside support hours:** for Critical issues only, call +49 176 41565516. We will try to respond, but this is **best effort, not guaranteed**. The 1-hour Critical target applies within support hours.
**Uptime commitments:** none. We do not guarantee any uptime percentage.
**How to submit requests:** +49 176 41565516 (phone and WhatsApp) or info@faiyke.com. There is no ticket portal yet. Critical issues should be phoned in, not emailed.
**Escalation:** if a ticket misses its target or the client is unhappy, escalate to the owner by phone (+49 176 41565516) or email (info@faiyke.com).

## Reporting
A monthly report on the Essential and Complete plans: tickets opened and closed, response times against the targets, patch status, device health, and security events.

## Common questions
**How much does managed IT cost?**
Give the plan range per user or device (net, plus VAT), then ask team size and needs. Mention the 12-month contract and that there is no setup fee.

**What if we already have an IT person?**
We can discuss supplementing them, for example with monitoring. The team confirms what's possible; offer to pass the question on.

**Can AI handle our help desk tickets?**
An AI agent can take requests, collect the details, and create well-formed tickets in your PSA, and it can check device health. A technician approves any action that changes a device. Stress security, guardrails, human approval, and starting with one workflow.

**Do you support on-site?**
We haven't confirmed on-site support. Don't say yes or no. Offer to ask the team and take the customer's details.

**How fast will you respond?**
Give the response target for the priority (Critical 1 hour, High 4 business hours, Normal 1 business day, Low 2 business days) within support hours (Mon–Fri 8:00–18:00). Say these are targets, not guarantees, and that response is not the same as a fix.

**Is there 24/7 support?**
No. For Critical issues outside support hours, the customer can phone +49 176 41565516. We try to respond, but it is best effort and not guaranteed.

**Can you help after a cyberattack?**
This is urgent: tell them to disconnect the affected device from the network and call +49 176 41565516, then escalate immediately per `../general/contact-escalation.md`. Don't give other recovery instructions.

**Are you compliant with HIPAA / PCI / etc.?**
Don't claim compliance unless documented. Escalate.

## Next step
Qualify using `../general/lead-qualification.md` (users, devices, current setup, pain points), then offer an assessment or call. There is no booking link yet, so arrange a call by phone, WhatsApp (+49 176 41565516), or email (info@faiyke.com).
