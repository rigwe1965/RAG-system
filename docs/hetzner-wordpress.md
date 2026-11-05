# Deploy on Hetzner and add to WordPress

Use a **separate small server** for the chat (Hetzner Cloud, type CX22 or similar, about €4–5/month, location Falkenstein or Nuremberg, Ubuntu 24.04). Do not put it on the same server as WordPress: both want ports 80/443.

## 1. Create the server (10 min)

1. console.hetzner.cloud → new project → **Add server**: Ubuntu 24.04, Germany, add your SSH key. Note the server's IP.
2. At your domain provider, add a DNS **A record**: `chat.faiyke.com` → that IP. (Use your real domain if it differs; edit `deploy/Caddyfile` to match.)

## 2. Upload and install (10 min)

First make a normal login for yourself and shut the door on root (do this once, while still logged in as root; keep this
window open and test the new login in a second window before you close it):

```bash
ssh root@SERVER_IP
adduser deploy && usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh && cp ~/.ssh/authorized_keys /home/deploy/.ssh/ && chown -R deploy:deploy /home/deploy/.ssh
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/; s/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh
```

From your PC (PowerShell), in the project folder. Leave out `.env` if it holds keys from your own computer, and
create it on the server instead:

```powershell
scp -r . deploy@SERVER_IP:/home/deploy/faiyke
ssh deploy@SERVER_IP
```

On the server:

```bash
cd ~/faiyke
sudo bash deploy/setup.sh        # installs Python, Caddy (https), firewall, and the service
sudo nano /opt/faiyke/.env   # set ANTHROPIC_API_KEY and ALLOWED_ORIGINS=https://www.faiyke.com,https://faiyke.com
sudo systemctl restart faiyke-chat
curl https://chat.faiyke.com/health     # should print {"ok": true}
```

`.env` stays on the server. Never email it. Delete the uploaded folder (`rm -rf ~/faiyke`) once setup is done. The program files in `/opt/faiyke` belong to root on purpose; only the data folders (`handoffs`, `logs`, `sessions`, ...) belong to the chat service. Add the WhatsApp and SMTP values here later too.

## 3. Add it to WordPress

Easiest: plugin **WPCode** (or "Insert Headers and Footers") → Add snippet → HTML → location **Site-wide footer** → paste:

```html
<script src="https://chat.faiyke.com/widget.js"
        data-api="https://chat.faiyke.com"
        data-privacy-url="https://www.faiyke.com/datenschutz" defer></script>
```

Set the privacy URL to your real page. Save and activate. Caching plugins: clear the cache afterwards.

## 4. Test

Phone and PC: opening hours, a hair question, a German question, "I want to speak to a person" (check the hand-off email or `/opt/faiyke/handoffs/handoffs.jsonl`).

## Daily use

| Task | Command (on the server) |
|---|---|
| Status / logs | `systemctl status faiyke-chat` / `journalctl -u faiyke-chat -n 50` |
| After editing the knowledge base | upload the files to `/opt/faiyke/knowledge-base/` (with `sudo`), then `cd /opt/faiyke && sudo -u faiyke python3 -m rag.ingest && sudo systemctl restart faiyke-chat` |
| After editing `.env` | `systemctl restart faiyke-chat` |
| Updates | security updates install by themselves (`unattended-upgrades`); still run `apt update && apt upgrade` monthly and reboot when asked; turn on Hetzner backups (about 20% extra) |

Also sign Hetzner's data processing agreement (in the Hetzner console), and list the chat in your privacy policy.

## WhatsApp on the same server

The Hetzner server already has everything WhatsApp needs: a permanent https address and no tunnel. The webhook address is `https://chat.faiyke.com/webhook/whatsapp`. First do the Meta account steps in `docs/whatsapp-setup.md` (Part 1, steps 1 to 4, and Part 2, step 2 for the permanent token).

On the server:

```bash
nano /opt/faiyke/.env
```

Set `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN` (any secret word you choose) and `WHATSAPP_APP_SECRET` (Meta app: App settings → Basic → App secret). Then:

```bash
systemctl restart faiyke-chat
cd /opt/faiyke
sudo -u faiyke python3 -m rag.whatsapp_setup check                          # token and number are valid
sudo -u faiyke python3 -m rag.whatsapp_setup webhook https://chat.faiyke.com # must say OK
```

At Meta (app → WhatsApp → Configuration → Webhook → Edit): Callback URL `https://chat.faiyke.com/webhook/whatsapp`, Verify token = your `WHATSAPP_VERIFY_TOKEN`. Click **Verify and save**, then subscribe to the **messages** field.

Send a WhatsApp message to the number. Watch the log while you do: `journalctl -u faiyke-chat -f`. You should see the message arrive and a reply go out. Message text is never logged.
