# Faiyke RAG assistant

Answers customer questions from the `knowledge-base/` folder using keyword search (BM25) and Claude.
No third-party Python packages are needed (standard library only).

## Run it

```powershell
$env:ANTHROPIC_API_KEY = 'sk-ant-...'
python -m rag.ingest                  # rebuild the index after editing any knowledge-base file
python -m rag.assistant               # chat in the terminal (customer-safe mode)
python -m rag.assistant --show-sources
python -m rag.assistant --voice       # short spoken-style answers
python -m rag.assistant --include-drafts   # testing only: also uses (PROPOSED) values
python -m rag.assistant --log         # saves conversations to logs/ (personal data: see GDPR note)
python -m unittest discover -s tests -t .  # retrieval tests, no API key needed
```

Models: `RAG_MODEL` (default `claude-sonnet-5-5`) and `RAG_REWRITE_MODEL` (default `claude-haiku-5-5`) can be set as environment variables.

## How it works

1. **Index** (`rag/ingest.py`): splits each knowledge-base file by heading into chunks. Skips `TODO.md`. `CLAUDE.md`, `voice-guidelines.md`, `contact-escalation.md` and `lead-qualification.md` are not searched; they go into the system prompt on every request.
2. **Draft safety:** a chunk containing `(PROPOSED)` is hidden from customers. A chunk with unfilled `[placeholders]` is shown to the model with a warning not to state those values.
3. **Search** (`rag/retrieve.py`): BM25 with heading boosting and a small synonym list (cost = price, hours = open, and so on).
4. **Answer** (`rag/assistant.py`): Claude first rewrites the customer's message (any language) into an English search query, the top 6 chunks are retrieved, and Claude answers in the customer's language using only those chunks.
5. **API calls** (`rag/claude.py`): plain HTTPS to the Claude API. The `anthropic` package is not used because its compiled `jiter` library is blocked by Windows Application Control on this PC.

## Test with real conversations

```powershell
$env:ANTHROPIC_API_KEY = 'sk-ant-...'
python -m tests.live_check            # 24 scenarios, about 60 API calls (a few cents)
python -m tests.live_check hand       # only scenarios whose name contains "hand"
```

It prints PASS / FAIL / REVIEW for each scenario and writes the full transcript to `logs/live_check.md`: questions, answers, the search used, and the sources. Scenarios cover hours, hair facts, shipping and returns, German questions, prices, security, IT emergencies, an unknown question, a prompt-injection attempt, and hand-offs with and without consent. Hand-offs go to a temporary folder and no email is sent.

## Website chat and WhatsApp (`rag/server.py`)

```powershell
$env:ANTHROPIC_API_KEY = 'sk-ant-...'
python -m rag.server        # http://127.0.0.1:8080  (demo page with the chat button)
```

**Website widget:** the full step-by-step guide (hosting, https, embedding, testing) is in `docs/website-chat-setup.md`. The widget speaks English and German. Short version: put this on your site (the server must be reachable over https):

```html
<script src="https://YOUR-SERVER/widget.js" data-api="https://YOUR-SERVER"
        data-privacy-url="https://YOUR-SITE/datenschutz" defer></script>
```

and start the server with `$env:ALLOWED_ORIGINS = 'https://your-site.de'` so only your site can use it. The widget tells visitors they are talking to an AI, links your privacy page, and shows your phone/email if the server is down.

**WhatsApp (Meta Cloud API):** the full step-by-step guide is in `docs/whatsapp-setup.md`. Settings can go in a `.env` file (copy `.env.example`). Helper commands: `python -m rag.whatsapp_setup check`, `send <number>`, `webhook <public-url>`. Short version:

1. Create a Meta developer app with the WhatsApp product and a WhatsApp Business number (a number already used in the normal WhatsApp app must be moved to the Business Platform first).
2. Set: `WHATSAPP_TOKEN` (permanent token), `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN` (any secret string you choose), `WHATSAPP_APP_SECRET` (app secret).
3. The server needs a public https address (a hosting service, or a tunnel such as Cloudflare Tunnel for testing). In the Meta app, set the webhook to `https://YOUR-SERVER/webhook/whatsapp`, use your verify token, and subscribe to `messages`.
4. Webhooks without a valid Meta signature are rejected. New chats get a one-line "I'm Faiyke's AI assistant" message first. Only text messages are answered. Customers can write to you freely for 24 hours after their last message; starting a conversation yourself needs a Meta-approved template.

**Protection built in:** 15 messages per minute per visitor (`RATE_LIMIT_PER_MIN`), 2000 messages a day in total (`DAILY_MESSAGE_CAP`) so a bot or spike cannot run up your Claude bill, 1000 characters per message, conversations forgotten after 30 minutes, message content never written to the server log.

- **One visitor cannot use up the day for everyone:** each visitor (IP address, or WhatsApp number) may use at most 10% of the daily cap (`PER_VISITOR_DAILY_SHARE`).
- **Real visitor address (`rag/netaddr.py`):** limits and login lockouts use the visitor's real address. `X-Forwarded-For` is believed only when the connection comes from a trusted proxy (`TRUSTED_PROXIES`, default `127.0.0.1,::1`, which is right for Caddy on the same server), and only the part the proxy added. Without this, every visitor behind Caddy looked like `127.0.0.1`, so five wrong passwords from anyone locked the owner out of `/admin`. Set `TRUSTED_PROXIES=none` if nothing sits in front of the server.
- **Admin only from your address:** `ADMIN_ALLOWED_IPS` (comma list, networks allowed) limits `/admin` to those addresses; everyone else gets "not found". `deploy/Caddyfile` does the same at the proxy and ships closed: edit the `remote_ip` line to your fixed IP and run `sudo systemctl reload caddy` (I could not test Caddy here), or use an SSH tunnel. The admin password is checked with a salted scrypt hash, not plain SHA-256. Still not done: a second factor.
- **Only your own links in answers (`rag/links.py`):** after the model writes an answer, every web address that is not yours is replaced by "[link removed]" (WhatsApp would make it tappable). Kept: `faiyke.com`, the hosts of `BOOKING_URL` and `PRIVACY_URL`, and `LINK_ALLOWED_DOMAINS`. Look-alikes such as `faiyke.com.evil.example` or `faiyke.com@evil.example` are refused. The web page applies the same rule while text is still streaming. Not covered: a bare domain without `http(s)://` or `www.`, and e-mail addresses.
- **Host-header checks:** the Hub answers only to local names (`127.0.0.1`, `localhost`, `[::1]`), which stops a web page on another site reaching it through your browser (DNS rebinding). `/admin` does the same for the names in `ALLOWED_HOSTS` (set in `deploy/faiyke-chat.service`).
- **Page script policy:** the chat page no longer allows `'unsafe-inline'` scripts. Its one inline script is allowed by hash, computed when the page is served, so text injected into the page cannot run. Do not add `onclick=` attributes or more inline scripts without keeping this in mind: a test fails if the page needs a blocked feature.
- **Hand-offs need a real "yes" in the chat:** the model fills in `consent` itself, so code now checks the conversation. The assistant must have asked to pass the details on, and the customer's next message must say yes (English or German, no "no" in it). Otherwise nothing is saved and the model is told to ask. Replies like "yes but not my email" count as no.

## Hand-off to a human

When a customer needs a person (upset, order problem, outage, custom quote, or unanswerable question), Claude calls the `escalate_to_human` tool. It only works once the customer has given their name, an email or phone number, and agreed to share their details (GDPR).

- Every hand-off is saved to `handoffs/handoffs.jsonl` with a reference like `FAI-20261104-001` and the recent conversation.
- To also get an email, set these before starting (Gmail needs an app password, not your normal password):

```powershell
$env:SMTP_HOST = 'smtp.gmail.com'
$env:SMTP_USER = 'iromanus@gmail.com'
$env:SMTP_PASSWORD = '<app password>'
# optional: $env:HANDOFF_TO = 'info@faiyke.com'
```

- If email is not configured or fails, the hand-off is still saved. Check `handoffs/` often until email is set up.
- Urgent IT issues: the assistant gives the emergency phone number first, then offers the hand-off.

## Before going live

- Remove `(PROPOSED)` markers from files you approve, then run `python -m rag.ingest`. Until then the assistant will not quote those prices and policies.
- Fill in the `[placeholders]` (see `knowledge-base/TODO.md`).
- Set up the email hand-off above and test it with a real message. A saved-but-unread hand-off is a lost customer.
- GDPR: `--log` stores personal data. Tell customers they are talking to an AI, say what is stored, and add it to your privacy policy.
- Streaming: answers appear word by word (`/api/chat/stream`, Server-Sent Events) in the chat page and the widget, with a Stop button. Browsers that cannot stream use `/api/chat`. Hidden markers are filtered out before anything is shown (`rag/streaming.py`). Behind Caddy, use `deploy/Caddyfile` (it turns off compression and buffering for the stream; I could not test Caddy here). `MAX_STREAMS` limits simultaneous streams.
- Follow-up suggestions (`rag/suggest.py`): two or three clickable next questions under the latest answer in the web chat and widget. The model adds them with a tool call at the end of its answer (no extra model call). Every suggestion is checked before it becomes a button: no links, emails, phone numbers, markup, hidden markers or attempts to instruct the assistant, and none after a hand-off. The model sometimes skips them; that is fine. Not used on WhatsApp or in voice mode.
- Admin dashboard (`rag/admin.py`): `python -m rag.admin setup` makes a strong password; put it in `.env` as `ADMIN_PASSWORD`, restart, open `/admin`. Off without a strong password (the page then answers "not found"). Put https in front of the server before using it from another computer. It shows:
  - **Activity** for the last 7, 30 or 90 days: messages per day (web, WhatsApp, failed), typical and slowest answer time, ratings per day, handoffs per day (and by business line), unanswered questions per day. Charts are drawn on the server as SVG, so the page still contains no JavaScript. The numbers come from `rag/metrics.py` (`metrics/metrics.db`): counts and times only, never a question, answer, name or contact detail; `METRICS=off` switches it off. History starts from the first message after you upgrade.
  - **Knowledge base:** when it was last indexed, which files changed since (customers still get the old text until you re-index), how many passages are still `(PROPOSED)` or have `[placeholders]`, which files were used most, and which were never used for an answer. The **Re-index now** button rebuilds the index in the background (about a minute with semantic search; the page refreshes by itself) and new chats use it at once. It is the dashboard's only action: it needs the login, a secret token and a same-site request, and only one runs at a time.
  - Bad ratings, unanswered questions (saved with emails and phone numbers removed; `LOG_GAPS=off` stops this), latest handoffs and settings.
- Privacy tools (`rag/privacy.py`): old records are deleted automatically (hand-offs 180 days, feedback 90, terminal logs 30; change with `RETENTION_*_DAYS`, 0 = keep). Customers can delete their own chat (server copy, ratings, saved chats in the browser) from the page and the widget. To handle a request yourself: `python -m rag.privacy erase --contact anna@example.com`, then delete the matching emails from your mailbox. `python -m rag.privacy status` shows what is stored. Set `PRIVACY_URL` so the chat links to your policy. Voice input asks for consent first, because the audio goes to the browser's speech service.

## Project Hub: one private query box over your projects (`rag/hub/`)

A second, private app next to the customer bot. It answers questions about the projects on your computer (how something works, how to run it, what an audit found, which projects use Neon, which ports clash) from their documentation, and shows the passages behind every answer.

```powershell
python -m rag.hub setup      # makes a password; put the HUB_PASSWORD=... line in .env
python -m rag.hub list       # the projects in hub/projects.json and what is indexed
python -m rag.hub ingest     # read them (a few seconds); repeat after docs change, or use the button on the page
python -m rag.hub serve      # http://127.0.0.1:8090/hub
```

- **What it reads is decided by `hub/projects.json`**: a list of projects (folder, which documentation files, aliases, `"cloud": true` to let a project go to Claude; local by default). Only `.md` and `.txt` files from the patterns you list. Add a project by adding an entry; anything not listed is invisible. The "What is indexed in this project" page lists every file that was read and every file that was skipped, and why.
- **Never read, whatever the config says:** `.env` files, anything named like a secret, key, token, password or credential, databases, `node_modules`, `.git`, virtual environments, build folders, `vault`, symbolic links and anything larger than 400 KB. A passage that looks like a secret (API keys, tokens, private keys, `PASSWORD=...`, `| Password | ... |`, connection strings with a password) is dropped whole and counted. Personal and third-party folders (`_Community`, `TPM_1`, `Apply_2023`, `Resume`, receipts, screenshots) are not registered.
- **Private:** listens on this computer only (any other `HUB_HOST` is refused), off until `HUB_PASSWORD` is a strong password, login limits, session cookie with its own name, secret token on every action, no JavaScript on the page, everything escaped, questions limited per minute (`HUB_RATE_PER_MIN`, 12) and per day (`HUB_DAILY_CAP`, 300). No question or answer is written to disk.
- **Projects are local until you say otherwise:** an entry without `"cloud": true` is never sent to Claude (its passages are only shown). Every project in `hub/projects.json` now states `cloud` explicitly. Review `crm`: it indexes source code and the database schema, and it is currently `"cloud": true`.
- **What goes to Claude:** when you ask, the matching passages (up to 8, about 1,400 characters each) and your question are sent to the Claude API, the same way the customer bot works. Passages are fenced and the prompt tells Claude they are data, never instructions, so a README cannot take control. Projects with `"cloud": false` are never sent; their passages are only shown.
- **How it searches:** keyword search per project (one index each, so projects do not mix). With "All projects", a project named in the question (its id, name or an alias) is searched on its own. If the optional local embedding model is installed (see "Semantic search" below), `python -m rag.hub ingest` also embeds every passage on this computer (`hub/index/vectors.npy`; nothing is sent anywhere) and questions are matched by meaning as well as by words, so different wording or German finds the right page. The very first ingest takes about 25 minutes for ~6,000 text windows; after that only new or edited text is embedded (a re-ingest with no changes takes seconds). Questions add milliseconds. Without the model, or with `EMBEDDINGS=off`, it silently stays keyword-only. Vectors that no longer match the passages are ignored.
- **Live data, read-only (`rag/hub/live.py`)**: projects with `"live": {"connector": ..., "db": ...}` in `hub/projects.json` also answer from their own database. Today: **AI Billing** (spend per month, provider and department; budgets against spend) and **ClaudeOS** (agent usage and failures, workflows, how much memory and output it holds). The model never writes SQL: it can only call fixed, validated lookups. Each query runs through `rag/hub/dbguard.py`: the file is opened read-only and SQLite itself refuses any column not on a per-tool allow-list, so password hashes, tokens, IP addresses, prompts and the text of runs and memories cannot be read even by mistake. Money is added up by code with exact decimals, per currency, never across currencies. Every answer states how old the database is, and every lookup is shown under the answer with the data it returned. Local-only projects get no live lookups. Add another source by writing its lookups in `live.py` and naming it in `registry.LIVE_CONNECTORS`.
- **Limits:** it knows the documentation and the live sources above, not the code and not other databases. Plans and audits describe intent and the past; answers say so when a passage comes from a plan. Project databases can be old or sample data: the answer says so.

## Chat design (`web/index.html`, `web/widget.js`)

The chat page and the website widget share one look and the same behaviours. Patterns were taken from current AI chat products and UX guidance (teaching empty state, named progress steps, visible sources, "not sure" as its own state with a way forward, a persistent route to a person, feedback with reasons, stop control, jump to latest).

- **Identity:** the mark is five strands, one per service line (hair, AI, website, IT, CRM), and those five colours recur in the starter questions and the source labels. Ink-violet is the shop's "natural black 1B", honey is "613 blonde" (primary actions). Light and dark follow the visitor's system; all text pairs pass WCAG AA.
- **While it works:** the avatar's strands sway and the line beside it names what is being read ("Checking Ordering, shipping & returns…"). The server sends the titles before the model starts (`rag/sourcelabels.py`; titles only, never file paths, only real knowledge-base files).
- **After the answer:** "Based on" labels show which parts of your information were used. When the assistant did not know (no match, an unconfirmed topic, or it said so) the labels are hidden and a quiet "Not sure about this one?" block offers **Talk to a person**. It is also always in the header. It starts the normal hand-off conversation: the assistant asks, and the customer must say yes (see "Hand-offs need a real yes").
- **Feedback:** thumbs-down offers one-tap reasons (wrong information, didn't answer, too long, something else) and an optional note. The reasons go through the existing feedback endpoint as the comment, so the admin dashboard shows them unchanged.
- **Controls:** Esc stops a running answer (as the Stop button does). If the reader scrolls up during a long answer, the page stops following and shows **Jump to latest**.
- **Not done:** the admin dashboard and the Hub keep their own plain styling; source labels are in English in the German page (titles come from the knowledge-base files).
- **Changing the page:** keep one inline script and no `onclick=` attributes (the script policy allows only that script, by hash). Files with Windows line endings are fine: the hash is taken the way browsers read the text. After editing, load the page in a real browser once; tests alone did not catch a blocked script before.

## Cookie banner and policy (`web/index.html`, `web/cookies.html`)

The chat page shows a banner (Continue / Reject, English and German) until the visitor chooses, and again from "Cookie settings" in the side panel. The policy is served at `/cookies` and lists every item the page can store.

- **Always on:** the visitor's banner choice (`faiyke_cookie_choice`), and, in the widget on other sites, a random chat number in session storage.
- **Only after "Continue":** saved chats, language, voice consent and read-aloud setting (`faiyke_chats_v1`, `faiyke_lang`, `faiyke_voice_ok`, `faiyke_autoread`). After "Reject", or before a choice, they live in memory for the tab only, and anything stored earlier is removed. A test fails if the page writes to local storage anywhere except through this gate.
- **No advertising, analytics or third-party cookies** exist in the project; the dashboards' login cookies (`fy_admin`, `fy_hub`) are for staff only and are listed in the policy.
- **Widget on your own site:** it cannot see your site's banner. Add `data-optional-storage="off"` to its script tag until your banner is accepted. Your own site's cookie policy should link to `/cookies` on this server or repeat its table.
- **If you add anything that stores data** (analytics, a new setting), add it to `web/cookies.html` in the same change. Have the wording checked by whoever advises you on privacy law; this is a technical implementation, not legal advice.

## Chats that survive a restart (`rag/sessionstore.py`)

Open chats are copied to `sessions/sessions.db` (SQLite, nothing to install) after every answer. After a restart or crash the customer simply carries on: the assistant still knows what was said, ratings still match, and WhatsApp does not repeat the "I'm Faiyke's AI assistant" line.

- **What is stored:** the recent messages (not the knowledge-base passages), the question text for rating matching (emails and numbers removed), and the time of the last message. The chat id is stored only as a hash, so no phone number sits in the file. Treat the file as personal data anyway: customers type names and emails into chats.
- **How long:** a chat is deleted 30 minutes after its last message. "Delete my chat" in the page or widget deletes it at once. `python -m rag.privacy erase --contact anna@example.com` also deletes open chats that mention that contact (and the WhatsApp chat of that number). `python -m rag.privacy status` shows how many are stored.
- **Limits:** at most 2000 stored chats, 20 messages and about 200 KB per chat. If the disk misbehaves, the chat carries on in memory and a line appears on stderr.
- **Switch off:** `PERSIST_SESSIONS=off`. Move the file with `SESSIONS_DIR`. Add the stored-chat sentence to your privacy policy.
- **Not done:** one SQLite file works for one server (or several on one machine). Several servers on different machines need a shared database; the store is one small class (`SessionStore`) to replace.

## Semantic search (optional, runs on your own computer)

Finds the right page even when the question uses different words, or is in German. Nothing is sent to a third party for searching.

```
pip install -r requirements-embeddings.txt
python -m rag.embed download     # one time, about 220 MB, checked against pinned hashes
python -m rag.ingest             # builds the keyword and the vector index (repeat after every knowledge-base edit)
python -m rag.embed check        # shows that it works
python -m tests.eval_embeddings  # measures the benefit and the similarity cutoff
```

If the extra, the model or the vector index is missing, out of date or fails its checks, the assistant quietly uses keyword search. Turn it off with `EMBEDDINGS=off`. Needs about 600 MB of RAM when running. Draft `(PROPOSED)` text stays hidden here too.

## Limits

- Keyword search misses meaning when the words differ a lot. Optional fix, done: local semantic search (see below). Without it the assistant uses keyword search only.
- Not tested against real WhatsApp or a live website (needs your Meta account and a public server). The server, signature check, and flows are covered by tests with fakes.
- Open chats are kept on disk for 30 minutes (see "Chats that survive a restart"), so a restart no longer ends them. Run it on a host that stays up (and behind https) for real use.
- No human takeover inside WhatsApp yet; a hand-off creates a record and optional email, and you reply yourself.
