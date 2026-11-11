# Deployment

The bot is one Python process with a SQLite file. It can run on a laptop, a small VPS,
a Raspberry Pi, or Docker. There is no Redis, worker queue or external database.

## Requirements

| Resource | Minimum | Comfortable |
| --- | --- | --- |
| CPU | 2 cores | 4 cores |
| RAM | 2 GB (3B model, quantized) | 8–16 GB for 7–8B models |
| Disk | 3 GB | 10 GB+ for multiple models and backups |
| Python | 3.11 | 3.12 / 3.13 |
| Network | outbound to GitHub; outbound to `api.telegram.org` / Slack / Matrix | |
| Public URL | only for the HTTP bridge / GitHub webhooks | |

Ollama can run on the same host or another machine. Set `OLLAMA_BASE_URL` accordingly.
If Ollama is remote, put it on a private network; the default API has no auth.

## Option A — local process

```bash
git clone https://github.com/cxy2696/GitHub-Community-Bot.git
cd GitHub-Community-Bot
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
$EDITOR .env
python -m github_community_bot --check
python -m github_community_bot
```

Run it under tmux/screen for a quick start, or systemd for a real deployment.

### systemd

Create a dedicated user and directory:

```bash
sudo useradd --system --create-home --home-dir /opt/github-community-bot communitybot
sudo -u communitybot git clone https://github.com/cxy2696/GitHub-Community-Bot.git /opt/github-community-bot/app
cd /opt/github-community-bot/app
sudo -u communitybot python3 -m venv .venv
sudo -u communitybot .venv/bin/pip install -e .
sudo -u communitybot cp .env.example .env
sudo -u communitybot mkdir -p data
sudo -u communitybot chmod 600 .env
```

`/etc/systemd/system/github-community-bot.service`:

```ini
[Unit]
Description=GitHub Community Bot
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User=communitybot
Group=communitybot
WorkingDirectory=/opt/github-community-bot/app
EnvironmentFile=/opt/github-community-bot/app/.env
ExecStart=/opt/github-community-bot/app/.venv/bin/python -m github_community_bot
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/github-community-bot/app/data
# If Ollama is local:
# After=ollama.service

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now github-community-bot
sudo systemctl status github-community-bot
sudo journalctl -u github-community-bot -f
```

Adjust `After=ollama.service` only if Ollama is a local systemd unit. A missing Ollama
does not prevent startup.

## Option B — Docker Compose

`docker-compose.yml` starts two services: Ollama and the bot. A one-shot service pulls
the model.

```bash
cp .env.example .env
# Set at least one platform token, or use the bridge.
# Generate a bridge secret:
python - <<'PY'
import secrets; print(secrets.token_hex(32))
PY
docker compose up -d
docker compose ps
docker compose logs -f bot
```

The bot persists `/data` in the `bot-data` volume and Ollama persists models in
`ollama-data`. The HTTP port is published on `8080`.

Important environment in Compose:

```dotenv
OLLAMA_BASE_URL=http://ollama:11434
DATA_DIR=/data
DATABASE_PATH=/data/community.db
```

If you prefer Ollama on the host, remove the `ollama` service and set
`OLLAMA_BASE_URL=http://host.docker.internal:11434` (Docker Desktop) or the host's
private IP (Linux).

### Pin versions for reproducibility

The example uses `ollama/ollama:latest` for convenience. In production, pin a tested
tag (for example the version printed by `ollama --version`) and pin the Python base
image digest. Update deliberately, not automatically on every restart.

## Reverse proxy and TLS

Expose only what you need. A public deployment usually needs `/api/v1/*` for the
bridge/webhook and optionally `/healthz`. Keep `/metrics` private.

### Caddy

```caddyfile
bot.example.com {
    @api path /api/v1/*
    handle @api {
        reverse_proxy 127.0.0.1:8080 {
            transport http {
                read_timeout 120s
            }
        }
    }
    handle /healthz {
        reverse_proxy 127.0.0.1:8080
    }
    respond 404
}
```

Caddy obtains TLS automatically.

### Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name bot.example.com;
    # ssl_certificate ...;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        client_max_body_size 1m;
    }

    location = /healthz {
        proxy_pass http://127.0.0.1:8080;
    }
}
```

The app does not require proxy headers; `TRUST_PROXY_HEADERS` exists for deployments
that later add IP-based logic.

## Model management

```bash
ollama pull qwen2.5:3b
ollama list
curl -s http://127.0.0.1:11434/api/tags | head
```

For multilingual quality, `qwen3:8b` is a strong upgrade if the host has RAM. For
low-power devices, `qwen2.5:1.5b` is faster but less reliable. Set `OLLAMA_MODEL`
and restart the bot.

If the model is not pulled, the bot still starts; `/status` says `degraded` and prints
the exact pull command.

## Updating

```bash
# Always back up first
scripts/backup.sh data/community.db backups

git pull --ff-only
source .venv/bin/activate
pip install -e .
python -m github_community_bot --check
sudo systemctl restart github-community-bot
```

Migrations run automatically at startup. They are additive in v2; take a backup
before a major version regardless. For Docker:

```bash
docker compose build bot
docker compose up -d bot
docker compose logs -f bot
```

Rollback: stop, restore the previous database backup if a migration changed the
schema, check out the previous tag, reinstall, start.

## Backups

`scripts/backup.sh` uses SQLite's online backup API, so it is safe while the bot is
running:

```bash
scripts/backup.sh data/community.db backups
# backups/community-20261111T143000Z.db.gz
```

Restore only while the bot is stopped:

```bash
sudo systemctl stop github-community-bot
scripts/restore.sh backups/community-20261111T143000Z.db.gz data/community.db
sudo systemctl start github-community-bot
```

Schedule a daily backup with cron:

```cron
15 3 * * * cd /opt/github-community-bot/app && scripts/backup.sh data/community.db backups >> /var/log/community-bot-backup.log 2>&1
```

Copy backups off the host. A backup on the same disk is not a disaster plan.

## Health and monitoring

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/readyz
curl -fsS http://127.0.0.1:8080/metrics | head
```

Use `/healthz` for liveness and `/readyz` for readiness. Both are cheap. `/readyz`
returns 503 if SQLite is unavailable or no adapter is ready; it does not fail just
because Ollama is down.

Suggested alerts:

- `/readyz` failing for 2 minutes;
- `ollama` status offline/degraded for 15 minutes (features degrade but core still works);
- `bot_adapter_start_errors_total` increasing;
- disk usage above 80% (models and WAL files);
- backup file missing for 48 hours.

## Multiple communities

Run one process per community/repository. Each process needs its own `DATA_DIR`,
database and HTTP port. Do not point two processes at the same SQLite file.

## Platform-specific deployment notes

- **Discord:** only outbound HTTPS. No public URL. Global slash command propagation is
  eventually consistent.
- **Slack:** Socket Mode is outbound WebSocket. No request URL, no public port.
- **Telegram:** long polling is outbound HTTPS. Do not configure a webhook.
- **Matrix:** outbound HTTPS to the homeserver. The bot must be invited to unencrypted
  rooms.
- **Bridge/webhooks:** require a public HTTPS endpoint or a private tunnel.
