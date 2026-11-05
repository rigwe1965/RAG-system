# Put the chat on your website (step by step)

The chat has two parts: the **server** (answers questions; this project) and the **widget** (a small script that adds the chat button to your site). The widget is ready in English and German; it picks the language from the page (`<html lang="de">`) or the visitor's browser.

## 1. Try it on your own PC (10 minutes)

```powershell
cd "C:\Users\rigwe\Desktop\RAG system"
copy .env.example .env        # then open .env and set ANTHROPIC_API_KEY
python -m rag.server
```

Open http://127.0.0.1:8080 in your browser. You'll see a demo page with the chat button at the bottom right. Ask a few questions. This works without a website or any other setup.

Run `python -m tests.live_check` first if you haven't: it checks the answers on 23 realistic scenarios.

## 2. Put the server on the internet

Your website needs to reach the server over **https**, so it must run on a machine that is always on. Options:

- **A small cloud server (VPS)** in the EU, for example from Hetzner (a German provider, convenient for data protection). Around a few euros a month is enough. This is the option the steps below assume.
- **A platform service** such as Render or Fly.io. Choose an EU region. Copy the project, set the same values as in `.env` as environment variables, and use `python -m rag.server` as the start command, with `HOST=0.0.0.0`.

Steps on a Linux server:

1. Install Python 3.10 or newer, copy the project folder to the server, and create `.env` there (never copy it by email).
2. Keep the server private and let a web server handle https. Install **Caddy** (it gets and renews https certificates automatically) and use this `Caddyfile`:

```
chat.faiyke.com {
    reverse_proxy 127.0.0.1:8080
}
```

   Point the DNS record `chat.faiyke.com` (or any name you like) to the server's IP. Keep `HOST=127.0.0.1` so only Caddy can reach the server. This also makes the per-visitor rate limit work correctly.

3. Run the server as a service so it restarts after a reboot (for example a `systemd` service running `python -m rag.server` in the project folder).
4. In `.env`, set `ALLOWED_ORIGINS` to your website, for example `ALLOWED_ORIGINS=https://www.faiyke.com,https://faiyke.com`. Only these sites can use the chat.
5. Check it: open `https://chat.faiyke.com/health`. It should show `{"ok": true}`.

## 3. Add the chat to your website

Add this just before `</body>` on every page where you want the chat (use your real addresses):

```html
<script src="https://chat.faiyke.com/widget.js"
        data-api="https://chat.faiyke.com"
        data-privacy-url="https://www.faiyke.com/datenschutz" defer></script>
```

| Website platform | Where to put it |
|---|---|
| WordPress | A "header and footer scripts" plugin, or `footer.php` of your theme |
| Shopify | Online Store → Themes → Edit code → `theme.liquid`, before `</body>` |
| Wix | Settings → Custom code → add to "Body – end" |
| Squarespace | Settings → Advanced → Code Injection → Footer |
| Webflow | Project settings → Custom code → Footer code |
| Plain HTML | Paste it in each page |

Force a language with `data-lang="de"` or `data-lang="en"` if you don't want automatic detection.

## 4. Test it on the live site

- Open the site on a phone and a computer. Ask: opening hours, a hair question, a price, a German question, "I want to speak to a person".
- Try the chat from a site that is **not** in `ALLOWED_ORIGINS`; it should refuse.
- Test a hand-off with your own email address and check that you receive it (see the README for the email settings).
- Check that the privacy link in the chat notice opens your privacy page.

## 5. Keep it up to date

- The knowledge base is loaded when the server starts. After you edit any file in `knowledge-base/`, run `python -m rag.ingest` and **restart the server**.
- Watch the cost: the server stops answering after `DAILY_MESSAGE_CAP` messages a day (default 2000) and limits each visitor to `RATE_LIMIT_PER_MIN` messages a minute. Lower the cap while you are testing.
- Check `handoffs/handoffs.jsonl` (or your email) every day until you are sure hand-offs reach you.

## Data protection (Germany / EU)

- The widget says in the chat that visitors are talking to an AI and links your privacy page.
- It stores only a random chat ID in the browser's session storage (no cookies, no tracking). The widget also remembers the read-aloud and voice-input settings in local storage; add `data-optional-storage="off"` to the script tag until your own cookie banner has been accepted, and that stops too. The server keeps each conversation in memory for 30 minutes and does not write message content to its log. Hand-off details are saved only after the visitor agrees.
- Mention in your privacy policy: the AI chat, that Anthropic (Claude) processes the messages, what is saved in a hand-off and for how long, and whom customers can ask about their data. Sign the data processing terms with Anthropic, and with your hosting provider.
- Have a lawyer review the privacy policy and Impressum before launch. This guide is not legal advice.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| No chat button on the site | The script address is wrong, or the page blocks external scripts. Open the script address in the browser; it should show JavaScript. |
| Button shows, but messages fail | The site is missing from `ALLOWED_ORIGINS` (check spelling, `https://`, with or without `www`). Restart the server after changing `.env`. |
| "Sorry, I can't connect right now" | The server is down or the address in `data-api` is wrong. Open `/health`. |
| Answers are old | You edited the knowledge base but didn't run `python -m rag.ingest` and restart. |
| Everyone gets blocked after a few messages | The server is directly exposed and sees one address for everyone; put it behind Caddy and keep `HOST=127.0.0.1`. |
| Answers say "I don't have that detail" too often | Check `logs/live_check.md` and the file that should answer it. Tell me the question and I'll fix the knowledge base. |
