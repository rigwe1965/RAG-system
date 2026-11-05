#!/usr/bin/env bash
# Run as root on a fresh Ubuntu 22.04/24.04 server, from the uploaded project folder:
#   sudo bash deploy/setup.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run with sudo"; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"

apt-get update
apt-get install -y python3 ufw debian-keyring debian-archive-keyring apt-transport-https curl gpg
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update && apt-get install -y caddy
fi

id faiyke >/dev/null 2>&1 || useradd --system --home /opt/faiyke --shell /usr/sbin/nologin faiyke
mkdir -p /opt/faiyke
if [ "$SRC" != "/opt/faiyke" ]; then
  # Copy the program, not the data from the computer it was built on: customers' hand-offs, chats, ratings and logs,
  # and the private Project Hub (its settings list folders on that computer) must not end up on the server.
  # (.env is copied if it exists: it holds this server's settings. Check it, and delete the uploaded folder afterwards.)
  tar -C "$SRC" \
    --exclude='./handoffs' --exclude='./sessions' --exclude='./feedback' --exclude='./gaps' --exclude='./metrics' \
    --exclude='./logs' --exclude='./hub' --exclude='./.git' --exclude='__pycache__' -cf - . | tar -C /opt/faiyke -xf -
fi
mkdir -p /opt/faiyke/handoffs /opt/faiyke/logs
[ -f /opt/faiyke/.env ] || { cp /opt/faiyke/.env.example /opt/faiyke/.env; echo ">> Edit /opt/faiyke/.env now (API key, ALLOWED_ORIGINS)"; }
chown -R faiyke:faiyke /opt/faiyke
chmod 600 /opt/faiyke/.env
(cd /opt/faiyke && sudo -u faiyke python3 -m rag.ingest)

cp /opt/faiyke/deploy/faiyke-chat.service /etc/systemd/system/
cp /opt/faiyke/deploy/Caddyfile /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable --now faiyke-chat
systemctl restart caddy

ufw allow OpenSSH; ufw allow 80/tcp; ufw allow 443/tcp
ufw --force enable
echo "Done. Check: systemctl status faiyke-chat ; curl https://chat.faiyke.com/health"
