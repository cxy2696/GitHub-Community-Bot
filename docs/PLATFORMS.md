# Platform setup

The engine is platform-neutral. Each adapter translates between a chat platform's
events and the shared `IncomingMessage` / `Reply` values. You can run any
combination at once — for example Discord and Telegram from the same database.

| Platform | Transport | Public URL needed? | Built-in |
| --- | --- | --- | --- |
| Discord | Gateway + slash commands | No | Yes |
| Slack | Socket Mode WebSocket | No | Yes |
| Telegram | Bot API long polling | No | Yes |
| Matrix | Client-server `/sync` | No (outbound) | Yes |
| Generic bridge | HTTP POST + HMAC | Yes, for remote apps | Yes |
| CLI | Terminal | No | Yes |

---

## Discord

### Create the application

1. Open <https://discord.com/developers/applications> → **New Application**.
2. **Bot** → **Add Bot** → **Reset Token** and copy the token.
3. Enable **Message Content Intent** under Privileged Gateway Intents. Without it,
   prefix commands and natural mentions cannot be read. Slash commands still work.
4. **OAuth2 → URL Generator**: scopes `bot` and `applications.commands`; permissions
   `View Channels`, `Send Messages`, `Read Message History`, `Embed Links`.
5. Open the generated URL and invite the bot. Slash commands are global and may take
   a few minutes to appear after the first sync.

### Configure

```dotenv
DISCORD_BOT_TOKEN=your-token
DISCORD_ADMIN_IDS=123456789012345678
DISCORD_CHANNEL_IDS=
DISCORD_SYNC_COMMANDS=true
```

- **Admin IDs:** enable Discord Developer Mode → right-click your avatar → Copy User
  ID. Multiple IDs are comma-separated.
- **Channel IDs:** optional allowlist. Empty means every channel the bot can read.
  DMs are always allowed.
- The bot replies in DMs, when mentioned, or when a message starts with a configured
  prefix (`!` or `/` by default).

### Slash commands

`/help`, `/start`, `/challenge`, `/leaderboard`, `/link`, `/ask`, `/sentiment`,
`/language`, `/privacy`, `/status`. `/link`, `/language`, `/privacy` and `/status`
reply ephemerally.

If commands do not appear, check the log for “Synced … slash commands”. Global
command propagation can take a few minutes. Set `DISCORD_SYNC_COMMANDS=false` if you
manage commands yourself.

---

## Slack

Slack uses **Socket Mode**, so you do not need a public request URL.

### Create the app

1. Open <https://api.slack.com/apps> → **Create New App** → **From an app manifest**.
2. Paste [`examples/slack-manifest.yaml`](../examples/slack-manifest.yaml), choose
   your workspace, and create the app.
3. **Basic Information → App-Level Tokens** → generate a token with the
   `connections:write` scope. This is `SLACK_APP_TOKEN` (`xapp-…`).
4. **Install App** → install to the workspace, then copy the **Bot User OAuth Token**
   (`xoxb-…`) as `SLACK_BOT_TOKEN`.
5. Invite the bot to each channel: `/invite @GitHub Community Bot`.

```dotenv
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_ADMIN_IDS=U0123456789
SLACK_CHANNEL_IDS=
```

- The bot answers DMs and `@mentions`; in channels it replies in a thread.
- Admin IDs are Slack member IDs (profile → **Copy member ID**).
- `SLACK_CHANNEL_IDS` is optional; empty means all channels the bot is in.
- If the app token is wrong, the log reports
  `apps.connections.open failed: invalid_auth`.

### Scopes used

`app_mentions:read`, `chat:write`, `im:history`, `users:read`. Add
`channels:history` only if you later want the bot to read non-mention channel
messages; the current adapter intentionally ignores those to reduce noise and
permissions.

---

## Telegram

### Create the bot

1. Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
2. Add the bot to a group, or open a DM.
3. For group use, either mention the bot (`@your_bot help`) or use commands
   (`/help`). Telegram's default privacy mode already limits the bot to mentions and
   commands, which matches the adapter's behavior.

```dotenv
TELEGRAM_BOT_TOKEN=123456789:AA...
TELEGRAM_ADMIN_IDS=987654321
TELEGRAM_CHAT_IDS=
```

- Admin IDs are numeric Telegram user IDs. `@userinfobot` can show yours.
- `TELEGRAM_CHAT_IDS` is optional; group IDs are usually negative
  (`-1001234567890`).
- The bot registers command menus in English, Chinese and Japanese at startup.
- **Do not set a webhook** while using long polling. If you previously set one,
  call `https://api.telegram.org/bot<TOKEN>/deleteWebhook`, otherwise `getUpdates`
  returns HTTP 409.

The last processed update offset is stored in SQLite, so a restart resumes cleanly.
On a brand-new database the bot skips the existing backlog instead of replying to old
messages.

---

## Matrix

Matrix support targets **unencrypted community rooms**. Encrypted rooms
(`m.room.encrypted`) are intentionally ignored: decrypting requires room keys and a
full E2EE client, and pretending otherwise would silently lose messages.

### Create a bot account and token

1. Create a dedicated account on your homeserver, e.g. `@community-bot:example.org`.
2. Obtain an access token. One option is:

```bash
curl -s -X POST https://matrix.example.org/_matrix/client/v3/login \
  -H 'Content-Type: application/json' \
  -d '{"type":"m.login.password","identifier":{"type":"m.id.user","user":"community-bot"},"password":"..."}'
```

3. Copy `access_token` from the response. Treat it like a password.
4. Invite the bot to the room and make sure the room is **not** encrypted.

```dotenv
MATRIX_HOMESERVER=https://matrix.example.org
MATRIX_USER_ID=@community-bot:example.org
MATRIX_ACCESS_TOKEN=syt_...
MATRIX_ADMIN_IDS=@alice:example.org
MATRIX_ROOM_IDS=!abc123:example.org
```

- `MATRIX_ROOM_IDS` is optional; empty means every joined room.
- The bot answers commands and messages that mention its full MXID.
- Admin IDs are full MXIDs.
- On first start the initial sync is discarded to avoid replying to room history.

---

## Generic HTTP bridge (any other chat app)

The bridge is how the bot reaches apps without a dedicated adapter: Feishu/Lark,
WeCom, LINE, Microsoft Teams, Zulip, Mattermost, a website widget, an n8n or Zapier
flow, or your own service. If your app can send an HTTP request and display the
response, it can use the bot.

### Enable it

```dotenv
HTTP_ENABLED=true
HTTP_HOST=0.0.0.0
HTTP_PORT=8080
BRIDGE_SHARED_SECRET=$(openssl rand -hex 32)
```

If `BRIDGE_SHARED_SECRET` is empty, the bridge endpoint returns `503` and is
effectively disabled — a safe default.

### Send a message

`POST /api/v1/messages`

Headers:

```text
Content-Type: application/json
X-Bridge-Timestamp: 1760000000          # optional but recommended
X-Bridge-Signature: sha256=<hex digest>
```

Signature:

```text
hex(HMAC-SHA256(secret, timestamp + "." + raw_body))   when timestamp is present
hex(HMAC-SHA256(secret, raw_body))                      otherwise
```

A timestamp outside ±300 seconds is rejected with `401 stale_timestamp`.

Body:

```json
{
  "text": "!help",
  "user_id": "u-123",
  "user_name": "Ada",
  "channel_id": "room-42",
  "locale": "zh-CN",
  "is_dm": true,
  "mentions_bot": false,
  "message_id": "msg-9001"
}
```

Response:

```json
{
  "ok": true,
  "request_id": "a1b2c3d4e5f6",
  "replies": [
    { "text": "…", "ephemeral": false, "kind": "message" }
  ]
}
```

The bridge never trusts a client-supplied admin flag. Admin access is controlled by
`BRIDGE_ADMIN_IDS` (user IDs). The platform name is fixed by
`BRIDGE_PLATFORM_NAME` (default `bridge`).

Run the included client:

```bash
BRIDGE_SHARED_SECRET=... python examples/bridge_client.py \
  --url http://127.0.0.1:8080 --user ada --text "!help"
```

See [`examples/bridge_client.py`](../examples/bridge_client.py).

### Notes

- Responses are synchronous: the HTTP request stays open while the bot replies. Put a
  reverse proxy timeout of at least 90 seconds if you use slow local models.
- The bridge does not persist chat messages, but it does not deduplicate repeated
  requests. Do not retry blindly after a timeout; make the request idempotent in your
  bridge or accept a duplicate command.
- Use TLS or a private network. HMAC protects integrity, not confidentiality.

---

## GitHub webhooks (optional, instant updates)

Polling every five minutes is enough for many communities. Webhooks make badge
updates instant and reduce GitHub API calls.

1. Expose the bot over HTTPS (reverse proxy, tunnel, or a public host).
2. In the repository: **Settings → Webhooks → Add webhook**.
3. Payload URL: `https://your-host/api/v1/github/webhook`
4. Content type: `application/json`.
5. Secret: the same value as `GITHUB_WEBHOOK_SECRET`.
6. Events: **Pushes**, **Issues**, **Pull requests** (the bot also answers `ping`).

```dotenv
GITHUB_WEBHOOK_SECRET=$(openssl rand -hex 32)
```

The endpoint verifies `X-Hub-Signature-256`. Events for a repository other than the
selected `GITHUB_REPO` are ignored. Polling remains enabled as a safety net;
activity keys make the two paths idempotent.

Supported awards:

| Event | Award |
| --- | --- |
| `push` | 10 points per commit, per commit author with a linked account |
| `issues` with `action=opened` | 20 points |
| `pull_request` with `action=opened` | 30 points |

---

## Adding a new adapter

1. Create `src/github_community_bot/platforms/your_platform.py`.
2. Subclass `PlatformAdapter`; implement `start`, `stop`, `deliver`.
3. Normalize an event into `IncomingMessage`, then call `await self.dispatch(incoming)`.
4. Build it in `app.build_adapters()` when its token is configured.
5. Add a platform-specific admin allowlist in `config.py`.
6. Add a small unit test for normalization; network calls stay out of tests.

Adapters import their SDK lazily so a missing optional dependency only affects that
platform. The engine has no platform-specific branches.
