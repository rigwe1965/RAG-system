# Connect WhatsApp (step by step)

The server code is ready (`rag/server.py`). What remains is account setup at Meta and putting the server on a public address. Menu names at Meta change from time to time; the ideas stay the same.

## What you need

- A Facebook account and a **Meta Business** account (business.facebook.com).
- A phone number for the assistant. It must **not** be in use in the normal WhatsApp or WhatsApp Business app (or it must be removed from there first). For testing you can use the free test number Meta gives you.
- Your Claude API key (console.anthropic.com).
- Python on the PC or server that will run the assistant.

## Part 1: Test it on your own PC (about 30–45 minutes)

### 1. Create the app

1. Go to developers.facebook.com, **My Apps → Create App**, type **Business**, connect your Meta Business account.
2. In the app, add the product **WhatsApp**.
3. Open **WhatsApp → API Setup**. Meta shows a **test phone number**, a **Phone number ID**, and a **temporary access token** (valid about 24 hours).
4. Under "To", add your own mobile number as a recipient and confirm the code. In test mode, only numbers you add here can receive messages.

### 2. Fill in `.env`

1. Copy `.env.example` to `.env` in the project folder.
2. Set `ANTHROPIC_API_KEY`, `WHATSAPP_TOKEN` (the temporary token), `WHATSAPP_PHONE_ID` (the Phone number ID, a long number, not a phone number), and `WHATSAPP_VERIFY_TOKEN` (make up any secret word).
3. `WHATSAPP_APP_SECRET`: in the app, **App settings → Basic → App secret → Show**.
4. `.env` holds secrets. Never email it, post it, or put it in a shared folder.

### 3. Check the settings

```powershell
cd "C:\Users\rigwe\Desktop\RAG system"
python -m rag.whatsapp_setup check
```

It lists missing values and asks Meta whether the token and number ID work.

### 4. Send a test message

```powershell
python -m rag.whatsapp_setup send 49XXXXXXXXXX
```

Use your mobile number with country code, digits only. Meta's "hello_world" message should arrive on your phone.

### 5. Start the server and open a tunnel

```powershell
python -m rag.server
```

In a second PowerShell window, create a temporary public address (free, no account) with Cloudflare's `cloudflared` tool (install it from developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads):

```powershell
cloudflared tunnel --url http://localhost:8080
```

It prints an address like `https://something.trycloudflare.com`. It changes each time you start it.

### 6. Check that Meta can reach you

```powershell
python -m rag.whatsapp_setup webhook https://something.trycloudflare.com
```

It must say OK.

### 7. Register the webhook at Meta

1. In the app: **WhatsApp → Configuration → Webhook → Edit**.
2. Callback URL: `https://something.trycloudflare.com/webhook/whatsapp`
3. Verify token: the same `WHATSAPP_VERIFY_TOKEN` as in `.env`.
4. Click **Verify and save**, then under "Webhook fields" **subscribe to `messages`**.

### 8. Chat with it

Send a WhatsApp message from your phone (the one you added in step 1) to the test number. You should get "Hi, I'm Faiyke's AI assistant." and then an answer. Test: opening hours, a hair question, a German question, "I want to speak to a person".

If nothing arrives, see "Troubleshooting" below.

## Part 2: Go live for real customers

1. **A permanent address.** The tunnel is for testing only. Run the server on a hosting service that stays online, with https (a small cloud server, or a platform like Render or Fly.io). Set `HOST=0.0.0.0` and the same `.env` values there. Note that chats are held in memory; a restart ends open conversations.
2. **A permanent token.** In Meta Business Settings, create a **System user**, give it the app with "Manage app" permission, generate a token with `whatsapp_business_messaging` and `whatsapp_business_management`, set it to never expire, and put it in `WHATSAPP_TOKEN`.
3. **Your own number.** In **WhatsApp → API Setup**, add your real business number and verify it with the code Meta sends. Put its new Phone number ID in `WHATSAPP_PHONE_ID`. Remove the number from the regular WhatsApp app first.
4. **Business verification and display name.** In Meta Business Settings, complete **Business verification** (company documents). Meta must approve your display name ("Faiyke") before you can message people outside the test list. Switch the app from Development to **Live** mode.
5. **Re-run the checks** (`check`, `webhook`) against the permanent address and update the webhook URL at Meta.
6. **Add it to your website** with a "Chat on WhatsApp" link: `https://wa.me/4917641565516`.

## Rules to know

- **24-hour window:** customers can message you any time and you can answer freely for 24 hours after their last message. To start a conversation yourself, you need a Meta-approved message template. This assistant only answers, so you don't need one for it.
- **Costs:** Meta charges per message or conversation depending on type and country; replies within the customer-service window are free or cheap, and prices change. Check Meta's current WhatsApp pricing page. Claude usage is billed separately by Anthropic.
- **Text only:** voice notes, images and files get the reply "I can only read text messages." You can extend this later.
- **Duplicate and flood protection:** the server ignores repeated deliveries and limits each customer to 15 messages a minute (`RATE_LIMIT_PER_MIN`), with a daily cap (`DAILY_MESSAGE_CAP`).

## Data protection (Germany)

- Tell people in your privacy policy that they are chatting with an AI, that WhatsApp (Meta) and Claude (Anthropic) process the messages, and that hand-off details are stored.
- Sign or accept the data processing terms with Meta and with Anthropic.
- The hand-off asks for consent before saving the customer's details.
- Have a lawyer check the wording of your privacy policy and Impressum.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `check` says Meta rejected the token | The temporary token expired (about 24 hours). Create a new one on the API Setup page, or use a System user token. |
| `webhook` says 403 | `WHATSAPP_VERIFY_TOKEN` in `.env` differs from the one at Meta, or the server was started before you changed `.env`. Restart the server. |
| `webhook` says it cannot reach the server | The server or tunnel is not running, or the tunnel address changed. |
| Meta says "callback URL or verify token couldn't be validated" | Same as above; run the `webhook` check first. |
| Messages arrive in the server log but no reply | Wrong `WHATSAPP_PHONE_ID` or expired token. Run `check`. |
| No log lines at all | Webhook field `messages` is not subscribed, or the sender is not on the test recipient list. |
| Server logs "403 bad signature" | `WHATSAPP_APP_SECRET` is wrong or from a different app. |
| `send` fails with a recipient error | The number is not on the allowed list in test mode, or has the wrong format. Use country code, digits only. |
