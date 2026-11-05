# IT Support & RMM: Remote Management

Explains how remote monitoring and management (RMM) works, in plain language. Use it for questions about agents, access, privacy, and what we can and can't do remotely.

> Items in [BRACKETS] are for the owner to fill in. Name only tools and capabilities you actually use.

## What RMM is
RMM (Remote Monitoring & Management) is software installed on your computers and servers. It lets us watch their health, apply updates, and fix many problems remotely, often before you notice them.

## What we monitor
- Device health: disk space, memory, CPU, hardware alerts
- Operating system and software patch status
- Antivirus/security status
- Backup success or failure
- Network devices and servers [if included]
- Uptime of key systems [if included]

## What we manage
- Scheduled OS and application updates
- Software installation and removal
- Scripts and automated fixes (e.g. clearing disk space, restarting services)
- Device inventory and asset tracking
- Security policies [e.g. disk encryption, screen lock]
- Remote support sessions for users

## How remote support works
1. User contacts us (phone, email, or portal), or an alert is raised automatically.
2. We check the device through the RMM tool.
3. With the user's permission [or silently for maintenance tasks, per agreement], we connect to fix the issue.
4. We document the work in the ticket.

## Tools
- **RMM platform:** [NAME, or "an industry-standard platform"]
- **Remote access tool:** [NAME]
- **Ticketing/PSA:** [NAME]
- **Security/EDR:** [NAME]
- **Documentation/password manager:** [NAME]

## Security & privacy
- The agent runs with administrative privileges, so access is limited to authorized technicians.
- [MFA is required for technicians and the management console.]
- [Remote sessions are logged.]
- We don't read personal files or monitor content. We monitor system health. [Confirm and adjust: some clients may ask about activity monitoring.]
- Remote sessions to a user's device happen [with permission / with notification].
- Data handling: [where logs and inventory are stored]

## What requires on-site or user action
- Failed hardware (disk, power supply, screen)
- Devices that won't power on or connect to the internet
- Physical network cabling
- Setup of new devices
- Anything where the device has no internet connection

## Supported systems
- **OS:** [Windows 10/11, macOS, Linux versions]
- **Servers:** [Windows Server, etc.]
- **Mobile:** [MDM for iOS/Android, if offered]
- **Not supported:** [list]

## AI agents with RMM / PSA
We can connect an AI agent to your RMM, PSA, and helpdesk tools. Full detail is in `../ai-agency/ai-agent-integrations.md`.

**Platforms we commonly integrate with:** NinjaOne, ConnectWise (RMM and PSA), Datto, Autotask, HaloPSA, Syncro, and Microsoft 365. [Confirm this matches the tools you actually support.]

**What the agent can do**
- Create, update, and close tickets with full context
- Query device health from the RMM
- Run approved scripts or stage fixes, **with technician approval**
- Gather missing information from the end user by voice, Teams, or email before a ticket is fully created
- Turn proactive alerts into structured tickets

**Guardrails we always apply**
- Least-privilege API keys: the agent gets only the permissions it needs
- Human-in-the-loop for any action that changes a device
- MFA everywhere
- Session logging and a full audit trail of every tool call
- A kill-switch to turn the agent off quickly

**How we roll it out:** start with one high-value workflow (for example, turning end-user requests into well-formed tickets), run in shadow mode where the agent suggests and a technician confirms, then expand step by step. Complex, high-security MSP setups typically take 6–10 weeks.

## Getting started
See `onboarding-security.md`. In short: assessment, install agents, apply baseline policies, begin monitoring.

## Common questions
**Will it slow down our computers?**
The agent is lightweight. [Describe typical impact.] Heavy tasks can be scheduled outside working hours.

**Can you see what my employees are doing?**
We monitor device health and security, not personal activity. [Confirm what's collected.]

**Do you need access to all our devices?**
Only devices covered by the plan need the agent. Per-device billing applies. [Confirm.]

**What if a device is off or offline?**
We can't reach it until it connects. Patches apply when it's next online.

**Can you work from outside our office?**
Yes, remote devices with the agent can be managed from anywhere with internet access.

**Can an AI agent fix things on our devices by itself?**
Not without a person. An agent can look up device health and stage a fix, but any action that changes a device needs technician approval. Everything is logged.

**Can AI create tickets for us?**
Yes. An agent can collect the details from the end user and create a structured ticket in your PSA. See `../ai-agency/ai-agent-integrations.md`.

**What happens if we cancel?**
[Agent removal process and data handling.]

## Escalation
Active incidents (suspected breach, ransomware, outage) go to a human immediately per `../general/contact-escalation.md`. Don't give hands-on troubleshooting steps beyond what's documented here.
