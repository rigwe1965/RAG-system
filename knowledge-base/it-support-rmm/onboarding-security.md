# IT Support & RMM: Onboarding & Security

How a new IT client gets started and the baseline security we set up. Don't claim certifications or compliance unless stated here.

> Items in [BRACKETS] are for the owner to fill in.

## Onboarding steps
1. **Discovery call:** team size, devices, systems, pain points, goals, budget.
2. **IT assessment:** [free/paid] review of devices, network, software, backups, accounts, and security. Output: a findings report and recommendations.
3. **Proposal & agreement:** plan, price, scope, SLA, and contract.
4. **Kickoff:** confirm contacts, schedule, and communication.
5. **Documentation:** inventory of devices, accounts, licenses, network, vendors, and passwords (in a secure vault).
6. **Deployment:** install RMM agents, endpoint protection, and policies. [Staged to limit disruption.]
7. **Security baseline:** see below.
8. **User introduction:** how to get support, who to call, what to expect.
9. **Go live** and regular reviews.

**Typical timeline:** [e.g. 2–4 weeks depending on size]

## What we need from the client
- Primary contact and authority to approve changes
- List of users, devices, and software
- Admin access to key systems (domain, email, firewall, cloud) via a secure method
- Details of the current IT provider, if any, and handover cooperation
- Contracts, licenses, and warranties
- Any compliance requirements

> Don't send passwords by email or chat. We use [secure method].

## Security baseline
Standard protections we put in place [confirm each]:
- **Multi-factor authentication (MFA)** on email and critical systems
- **Endpoint protection** (antivirus/EDR) on all devices
- **Patch management:** OS and software updates on a schedule
- **Backups:** automated, monitored, with periodic restore tests
- **Firewall and network review**
- **Email security:** spam, phishing, and malware filtering
- **Account hygiene:** least-privilege access, removal of old accounts, password manager
- **Disk encryption** on laptops
- **Security awareness training** [if included]
- **Offboarding process** to remove access quickly

## Optional / advanced
- Web filtering and DNS security
- Mobile device management
- Security monitoring (SIEM/SOC) [if offered]
- Vulnerability scanning
- Compliance support: [e.g. HIPAA, PCI, cyber insurance requirements. Describe exactly what you do and don't provide.]
- Incident response planning

## Ongoing
- Regular patching and monitoring
- Monthly or quarterly reviews: [what's covered]
- Reporting: [describe]
- Annual IT planning and budgeting [vCIO]

## AI agent security & governance
If an AI agent is connected to your RMM, PSA, or helpdesk (see `remote-management.md` and `../ai-agency/ai-agent-integrations.md`), we apply these controls:

- **Least privilege:** the agent gets only the minimum permissions needed, through narrow, approved actions (APIs, webhooks, or MCP servers).
- **Human-in-the-loop:** any device-changing, irreversible, or high-value action needs technician approval.
- **MFA everywhere.**
- **Audit trail:** session logging and a complete record of every tool call.
- **Data isolation:** one customer's data is never exposed to another. We authenticate the user first and pass only verified identifiers into API calls.
- **Validation and rate limiting** on every write.
- **Kill-switch / feature flags** to turn the agent off quickly.
- **Compliance alignment:** GDPR and data residency where required. [Confirm exactly what you can state.]
- **Rollout:** one high-value workflow first, in shadow mode (the agent suggests, a technician confirms), then limited autonomy.

## Employee joiner/leaver
- **New hire:** request via [PORTAL/EMAIL]; account and device ready in [X days].
- **Leaver:** request immediately; access disabled the same day [target].

## Incident response
- Suspected breach, ransomware, or stolen device: contact +49 176 41565516 immediately.
- Don't pay ransoms or delete anything. Disconnect the affected device from the network if it is safe to do so.
- The assistant should escalate at once per `../general/contact-escalation.md`.

## Common questions
**How disruptive is onboarding?**
Mostly behind the scenes. Some restarts and a short user briefing. [Describe.]

**What if our current provider won't cooperate?**
We can work with what we can access. Escalate to a human.

**Are you HIPAA/PCI/SOC 2 compliant?**
Only state what's documented here. Otherwise escalate.

**Will you secure our Microsoft 365 / Google Workspace?**
Yes: MFA, policies, and email protection. [Confirm.]

**Do you provide cyber insurance help?**
[Describe or escalate.] We can help meet common insurer requirements. We don't provide insurance.

**Is it safe to let an AI agent connect to our IT systems?**
Yes, when it's governed. The agent only calls approved tools with least-privilege access. A technician approves anything that changes a device. Every action is logged, and there's a kill-switch. We start with one workflow in shadow mode.

**Can you guarantee we won't be hacked?**
No one can. We reduce risk and respond quickly.

## Next step
Offer an assessment: [no booking link yet: arrange a call by phone, WhatsApp, or email]. Compliance, contract, and security-review questions go to a human per `../general/contact-escalation.md`.
