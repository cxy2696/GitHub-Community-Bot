# Operations runbook

This is the practical guide for keeping a deployment healthy. It assumes the bot runs
under systemd or Docker and exposes the HTTP server.

## Daily checks (2 minutes)

```bash
curl -fsS http://127.0.0.1:8080/readyz | jq
curl -fsS http://127.0.0.1:8080/metrics | grep -E 'bot_(errors|adapter_start)|ai_requests|http_errors'
systemctl is-active github-community-bot
df -h /opt/github-community-bot
```

`/readyz` 200 means the database is reachable and at least one adapter is up. AI and
GitHub are reported by `/status` and in logs, not by readiness.

## Logs

Text (default) is friendly for humans:

```bash
journalctl -u github-community-bot -f
# or
docker compose logs -f bot
```

JSON (`LOG_FORMAT=json`) is easier to ship:

```json
{"ts":"2026-11-11T06:30:00.000+00:00","level":"INFO","logger":"github_community_bot.bot","message":"Poll complete: 12 contributors, 3 new activities, 50 points"}
```

Secrets are redacted by the formatter. Redaction is a safety net, not a reason to log
tokens.

Useful grep targets:

```bash
journalctl -u github-community-bot | grep -E 'ERROR|Traceback|Poll failed|adapter'
```

## Runbooks

### The bot is not responding at all

1. `systemctl status github-community-bot` or `docker compose ps`.
2. Check the last 100 log lines for configuration or login errors.
3. Run `python -m github_community_bot --check` with the same environment.
4. `curl -i http://127.0.0.1:8080/healthz`. If this fails, the process is down or
   bound to another address/port; check `ss -ltnp | grep 8080`.
5. Restart. If it fails immediately, the log usually names the exact missing setting.

Common causes: expired Discord token, Slack app token without `connections:write`,
Telegram webhook conflict, a database path without write permission, HTTP port already
in use.

### One platform is offline, the others work

The adapter runs in its own task; a failure does not stop the process.

- **Discord:** `LoginFailure` means a bad/rotated token. Missing Message Content Intent
  causes messages to arrive empty, not a login error.
- **Slack:** `invalid_auth` on `apps.connections.open` means the app-level token is
  wrong or lacks `connections:write`. `missing_scope` means the bot token needs a
  reinstall after scope changes.
- **Telegram:** HTTP 409 means a webhook is still configured. Run
  `curl https://api.telegram.org/bot<TOKEN>/deleteWebhook`. HTTP 401 means a bad token.
- **Matrix:** 401/403 means a bad/expired access token; `M_UNKNOWN_TOKEN` requires a
  new login. The bot only reads unencrypted rooms.

`/status` shows each adapter as online/offline.

### Ollama is offline or “degraded”

```bash
curl -s http://127.0.0.1:11434/api/tags | jq
ollama list
ollama ps
```

- **Connection refused:** start Ollama (`ollama serve` or `systemctl status ollama`).
  In Docker, check `OLLAMA_BASE_URL=http://ollama:11434` and that both containers are
  on the same network.
- **Model not pulled:** run the exact command in `/status`, e.g.
  `ollama pull qwen2.5:3b`.
- **Timeouts:** the model may be too large for RAM/CPU. Try a smaller model, increase
  `OLLAMA_TIMEOUT_SECONDS`, or reduce `OLLAMA_MAX_TOKENS`. The first request after a
  cold start is slower.
- **Very slow / swap:** check `ollama ps` and memory. A 14B model on an 8 GB host will
  thrash.

The bot keeps working with deterministic fallbacks. There is no need to stop it.

### GitHub commands fail or points stop updating

1. Check `/status`; GitHub shows `offline` or `degraded`.
2. Verify the token and scopes:

```bash
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user | jq .login
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/OWNER/REPO | jq .full_name
```

3. Check the rate limit:

```bash
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/rate_limit | jq
```

Search API has a separate, smaller quota; the code falls back to a paginated scan when
search is exhausted.

4. Look for `Poll failed for USER` in logs. A single user failure does not block the
   others.
5. If you use webhooks, check **Recent Deliveries** in GitHub repository settings. A
   401 means the secret does not match; a 503 means `GITHUB_WEBHOOK_SECRET` is unset.
6. If the repository was renamed, run `!set_repo owner/new-name`.

### Points look wrong

- Points are tied to the GitHub account, not the chat account. Linking the same GitHub
  account from two platforms does not duplicate history.
- Historical points are a baseline awarded at first link. Later points come from the
  event ledger.
- Duplicate webhook/poll events are ignored by `event_key`. If you suspect corruption,
  back up first, then inspect:

```bash
sqlite3 data/community.db \
  'select github_user, points, badges, last_activity_check from links order by points desc;'
sqlite3 data/community.db \
  'select count(*), github_user from activity_events group by github_user;'
```

Do not edit points while the process is running.

### Database is locked or `/readyz` is 503

- Run exactly one bot process per database file.
- `PRAGMA journal_mode=WAL` is enabled automatically; make sure the directory is
  writable, not just the file.
- Check disk space. A full disk breaks WAL writes.
- Long-running manual `sqlite3` transactions can block writes; close them.
- If the file is corrupted, restore the latest backup; do not run `VACUUM` on a
  suspected-corrupt database before copying it aside for diagnosis.

### A member linked the wrong GitHub account

An admin can unlink without deleting the member:

```text
!unlink discord:123456789012345678
!unlink telegram:987654321
!unlink bridge:u-123
```

Then the member runs `!link correct-username`. If the old GitHub account has no other
chat links, its score and ledger are removed by `unlink`.

### Privacy deletion request

Ask the member to send `!privacy delete confirm` in a **direct message**. The bot
removes the member, link mapping, and orphaned score/ledger. If they cannot DM, an
admin can delete the database row only after verifying the request out of band; follow
your community's policy and record the action.

Backups may still contain the data until they expire. Document your backup retention.

### Rotating a secret

1. Generate the new token/secret.
2. Update `.env` (permissions `600`).
3. For Discord/Slack/Telegram/Matrix, revoke the old credential at the provider.
4. Restart the bot.
5. For the bridge, deploy the new secret to callers at the same time; old signatures
   fail closed.
6. For GitHub webhooks, update the secret in repository settings and restart.

### Upgrading

```bash
scripts/backup.sh data/community.db backups
git fetch --tags
git checkout v2.1.0        # or the desired tag
source .venv/bin/activate
pip install -e .
python -m github_community_bot --check
sudo systemctl restart github-community-bot
curl -fsS http://127.0.0.1:8080/readyz
```

Migrations run at startup. Read `CHANGELOG.md` before a major upgrade.

### Rolling back

1. Stop the bot.
2. Check out the previous tag and reinstall.
3. If the database schema changed, restore the pre-upgrade backup (the migration is
   additive, but older code may not understand newer rows).
4. Start and verify `/readyz`.

### Restoring a backup

```bash
sudo systemctl stop github-community-bot
scripts/restore.sh backups/community-20261111T143000Z.db.gz data/community.db
sudo systemctl start github-community-bot
curl -fsS http://127.0.0.1:8080/readyz
```

`restore.sh` moves the current database to a timestamped `.pre-restore` file rather
than deleting it. Keep that file until you have verified the restore.

## Metrics reference

| Metric | Type | Meaning |
| --- | --- | --- |
| `bot_messages_total{platform}` | counter | normalized inbound messages |
| `bot_commands_total{command,platform}` | counter | recognized commands |
| `bot_rate_limited_total{platform}` | counter | messages rejected by the limiter |
| `bot_links_total{platform}` | counter | successful GitHub links |
| `bot_poll_runs_total` | counter | completed poll cycles |
| `bot_activity_awarded_total` | counter | new activity events awarded |
| `bot_errors_total{where}` | counter | handled errors by area |
| `bot_adapter_start_errors_total{adapter}` | counter | adapter startup failures |
| `ai_requests_total{task,result}` | counter | Ollama calls by task/outcome |
| `github_webhook_events_total{event}` | counter | accepted webhook events |
| `http_requests_total{method,path,status}` | counter | HTTP requests (route template) |
| `http_errors_total{path}` | counter | unhandled HTTP errors |
| `http_request_duration_seconds_sum` | counter | sum of HTTP durations |
| `bot_uptime_seconds` | gauge | process uptime |
| `bot_message_latency_seconds_sum` / `_count` | counter | sum/count of message handling time |

The latency values are sums/counts, not Prometheus histograms; compute an average as
`sum/count`. This keeps the registry dependency-free.

## Maintenance calendar

### Weekly

- Check `/readyz`, adapter status, and error counters.
- Review logs for repeated GitHub/Ollama failures.
- Confirm last night's backup exists and has a non-trivial size.

### Monthly

- Test a restore into a scratch directory (not production).
- Run `pip list --outdated` and review dependency updates; update in a branch and let
  CI run.
- Check disk usage for Ollama models and old backups.
- Review admin allowlists and remove departed maintainers.

### Quarterly

- Rotate bridge/webhook secrets.
- Review privacy policy and backup retention with the community.
- Re-read the roadmap and close stale issues.
- Test the bot with the current Discord/Slack/Telegram/Matrix APIs after major platform
  changes.

## Capacity notes

- A 3B model needs roughly 2–4 GB RAM depending on quantization and context.
- One Ollama request at a time is usually enough; concurrent requests queue in Ollama.
  The bot has no AI concurrency limit, so a busy channel can create a queue. Lower
  `RATE_LIMIT_PER_MINUTE` or run a larger host.
- SQLite handles this workload comfortably; the leaderboard is a single indexed query.
- GitHub polling cost grows with the number of linked users: one commits call and one
  issues call per user per cycle, plus a touch write. For large communities, enable
  webhooks and raise the poll interval to 15–30 minutes.

## Incident template

When something breaks, record:

```text
Time (UTC):
Symptom:
Affected platform(s):
Last deploy / config change:
/readyz output:
Relevant log lines (secrets removed):
Action taken:
Follow-up issue:
```

This makes post-incident improvements concrete and keeps the project sustainable.
