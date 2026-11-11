# Architecture

## Goals

1. **One brain, many chat platforms.** Platform code only translates. Everything
   else is shared and testable without a network.
2. **Free and local by default.** AI is an Ollama HTTP call, not a paid SDK.
3. **Useful when AI is down.** Challenges, tone reflection and chat have deterministic
   fallbacks; community features never depend on the model.
4. **Boring operations.** SQLite, one process, health endpoints, metrics, migrations
   and graceful shutdown. No Redis, Celery, Postgres or Kubernetes required.
5. **Kind by default.** Consent, DM-only deletion, no public shaming, no message
   retention.

## Non-goals

- Multi-tenant hosting for many unrelated communities in one process.
- Storing chat history or building a searchable archive.
- Diagnosing people or moderating automatically. Tone reflection is deliberately
  framed as a reflection, not a verdict.
- End-to-end encrypted Matrix rooms (see `docs/PLATFORMS.md`).

## Components

```text
┌──────────────────────────── application process ────────────────────────────┐
│                                                                              │
│  DiscordAdapter ─┐                                                           │
│  SlackAdapter ───┤                                                           │
│  TelegramAdapter ┼──► CommunityBot ──► Database (SQLite, WAL)                │
│  MatrixAdapter ──┤        │   │   │                                          │
│  CLIAdapter ─────┤        │   │   └──► OllamaClient ──► Ollama HTTP API      │
│  HTTPServer ─────┘        │   └──────► GitHubService ──► GitHub REST         │
│                           └──────────► I18n (en/zh/ja JSON)                  │
│                                                                              │
│  Metrics ◄── all components          Logging (text/JSON, redaction)          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### `CommunityBot` (`bot.py`)

The platform-neutral engine:

- parses commands and localized aliases;
- applies a sliding-window per-user rate limit;
- resolves locale (saved preference → platform hint → script → default);
- runs command handlers and AI calls;
- owns the GitHub poll loop and webhook event handling;
- exposes health/readiness information;
- never sends messages directly. It returns `list[Reply]`; adapters deliver them.

This boundary is the main reason the test suite can cover the whole product without
Discord, Slack, Telegram, Matrix or GitHub credentials.

### Adapters (`platforms/`)

Every adapter subclasses `PlatformAdapter`:

```python
async def start(bot): ...  # launch a task, do not block forever
async def stop(): ...  # cancel tasks and close sessions
async def deliver(channel_id, reply, *, thread_id=None): ...
```

Inbound normalization produces an `IncomingMessage` with a stable platform/user/
channel identity, locale hint, DM/mention flags and an admin flag computed from the
configured allowlist. Outbound messages are chunked to each platform's limit.

### `Database` (`storage.py`)

A small async wrapper around `sqlite3`:

- one connection, serialized by an `asyncio.Lock` and executed in worker threads;
- WAL mode, `busy_timeout`, foreign keys;
- schema version tracked with `PRAGMA user_version`;
- additive migrations applied at startup.

SQLite is a deliberate choice: the expected workload is a few hundred community
members and a handful of writes per minute. A single file is easy to back up and
inspect. If a community outgrows it, `Database` is the seam to replace.

### `OllamaClient` (`services/ai.py`)

- calls `POST /api/chat` with `stream: false`;
- 3 attempts with exponential backoff for transient failures;
- typed `AIError` reasons (`disabled`, `unavailable`, `timeout`, `model_missing`,
  `http_error`, `invalid_response`);
- health check via `GET /api/tags` with a 5-second timeout and cache;
- localized system prompts with safety and prompt-injection guardrails;
- a bounded in-memory conversation history (default 6 messages, 30-minute TTL) for
  natural follow-ups. It is not persisted.

### `GitHubService` (`services/github.py`)

- PyGithub for repository, commit and issue reads;
- a repository-wide async lock, because one PyGithub session is shared;
- 5-minute cache for historical totals (used by `link` and `challenge`);
- recent activity uses one issues call (GitHub returns PRs in the issues endpoint)
  plus commits;
- search API is used for one-time totals, with a paginated fallback when search rate
  limits are exhausted;
- all GitHub exceptions are mapped to `GitHubError` with an optional HTTP status.

### HTTP server (`platforms/http_server.py`)

`aiohttp` exposes:

| Path | Auth | Purpose |
| --- | --- | --- |
| `GET /healthz` | none | liveness, always 200 if the event loop is alive |
| `GET /readyz` | none | DB + adapter readiness; 503 when not ready |
| `GET /metrics` | none | Prometheus text exposition |
| `GET /version` | none | version |
| `POST /api/v1/messages` | HMAC-SHA256 | generic chat bridge |
| `POST /api/v1/github/webhook` | GitHub HMAC | instant contribution events |

Readiness deliberately does not call Ollama or GitHub. A model outage should degrade
features, not restart or remove the process from a load balancer.

## Data model

```text
members
  platform, user_id          PK
  display_name, locale, opted_out, timestamps

links
  github_user                PK (case-insensitive)
  points, badges, current_challenge, last_activity_check, timestamps

member_links
  platform, user_id          PK  → members
  github_user                    → links
  (many chat identities may share one GitHub account)

activity_events
  event_key                  UNIQUE  (commit:repo:sha, issue:repo:number, pr:repo:number)
  github_user, kind, points, source, title, url, timestamps

settings
  key, value, updated_at     (selected repo, Telegram offset)
```

### Identity: why points are on `links`

A person can use Discord and Telegram, and both identities should share one score.
Points therefore belong to the GitHub account. If a second chat account links the
same GitHub username, it attaches to the existing `links` row and sees the same
points; historical points are **not** added again.

A chat identity can link only one GitHub account at a time (`member_links` primary
key). To switch, an admin uses `!unlink platform:user`, then the member links again.

### Idempotency

`activity_events.event_key` is unique. Polling and webhooks both call
`award_for_user`; a duplicate key inserts nothing and awards nothing. This allows:

- polling and webhooks to run together;
- GitHub redeliveries;
- manual `!refresh` at any time;
- overlapping poll windows without double points.

Initial linking awards a **baseline** from historical totals. The ledger begins with
future activity. This avoids paging through every historical commit and issue.

## Message flow

```text
platform event
  → adapter normalizes IncomingMessage
  → engine.touch_member (profile/locale)
  → rate limit
  → command parse (localized aliases)
  → handler
      ├─ storage read/write
      ├─ GitHub (cached where possible)
      └─ Ollama (typed errors + fallback)
  → list[Reply]
  → adapter chunks and delivers
```

For the bridge, the same list is serialized in the HTTP response.

## GitHub flow

### Polling (default)

Every `GITHUB_POLL_INTERVAL_SECONDS` (minimum 60):

1. load links, each with `last_activity_check`;
2. fetch commits and issues/PRs created since that timestamp;
3. award each unseen event;
4. set `last_activity_check` to the **poll start time**, not completion time, so an
   event created during the poll is rechecked rather than lost;
5. errors are logged and that user is retried on the next cycle.

### Webhook (optional)

`push`, `issues.opened` and `pull_request.opened` are verified, normalized to the
same activity keys, and awarded immediately. Repository mismatches are ignored.
Polling remains as a backstop.

## Failure behavior

| Failure | Behavior |
| --- | --- |
| Ollama down / slow | Typed error, localized fallback or friendly notice; rest of bot works |
| Ollama model missing | `status` reports `degraded` with the exact `ollama pull` command |
| GitHub down / rate-limited | Command replies “try again shortly”; poll skips the user and retries |
| Database unavailable | `/readyz` 503; commands fail with a generic message; logs hold details |
| One adapter fails | Other adapters keep running; status shows it offline |
| HTTP port in use | Startup fails with a clear log line |
| Bad message handler bug | Caught, logged with context, user gets a generic apology |

## Security boundaries

- Secrets live only in environment variables / `.env`; logs redact common token
  formats.
- Adapters compute `is_admin` from configured allowlists; the bridge cannot assert it.
- Deletion requires a DM and an explicit `confirm`.
- Remote shutdown is disabled by default and still requires an admin.
- The bridge is disabled unless `BRIDGE_SHARED_SECRET` is set.
- Bridge signatures support an optional signed timestamp with a ±5 minute window.
- GitHub webhooks use the standard `X-Hub-Signature-256` HMAC.
- SQLite uses parameterized queries throughout.

## Extending

- **New platform:** one adapter + one config block + one `build_adapters` branch.
- **New command:** add a handler to `CommunityBot._handlers`, a translation key, a
  help line and a test.
- **New language:** add `locales/<code>.json`, add it to `SUPPORTED_LOCALES`, and make
  sure the key-parity test passes.
- **New point rule:** tune `POINTS` / `BADGE_THRESHOLDS` in `models.py`; storage and
  rendering read those constants.
- **New storage:** replace `Database` behind the same methods; the engine does not
  know SQL.

## Known limits

- Single-process SQLite; not designed for horizontal scaling.
- In-memory conversation memory and rate limits reset on restart.
- Global one-repository setting per process.
- Matrix E2EE unsupported.
- Slack slash commands require a public request URL; Socket Mode covers mentions/DMs
  but not slash command registration (roadmap).
- GitHub App authentication is not implemented; a PAT is simplest today.
