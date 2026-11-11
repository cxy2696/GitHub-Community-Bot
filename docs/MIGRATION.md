# Migrating from the v1 Gemini bot

v1 was a single `bot.py` using Gemini and a `user_data.db` keyed by Discord ID. v2 is
a platform-neutral package using local Ollama, a shared GitHub identity, and a
versioned schema.

## Recommended path: fresh start

Most communities only need the leaderboard, and a fresh score is cleaner than
preserving a Discord-only one.

1. Keep `DISCORD_BOT_TOKEN` and `GITHUB_TOKEN`.
2. Remove `GEMINI_API_KEY`; install Ollama and pull a model.
3. Back up the old checkout. If it is still named `GitHub-Discord-Bot`, keep it as
   `GitHub-Discord-Bot-v1`; the repository itself is now `GitHub-Community-Bot`.
4. Deploy v2 with the same tokens and a new `data/community.db`; remove the old
   `bot.py` and Gemini-era `requirements.txt` from the running deployment (keep a copy
   of `user_data.db` for the optional import).
5. Run `!set_repo owner/repo`.
6. Ask members to run `!link <github-username>` once. Their historical contributions
   become their baseline automatically.

Because points are tied to the GitHub account, a member who was on Discord can also
link from Slack/Telegram and share the same score.

## Optional: import the old leaderboard

Use this only if preserving v1 points matters. The bot must be stopped.

```bash
cp user_data.db backups/user_data-v1.db
python scripts/import_v1.py \
  --legacy backups/user_data-v1.db \
  --database data/community.db \
  --dry-run
```

Review the summary, then run without `--dry-run`.

The importer:

- reads `discord_id`, `github_user`, `points`, `badges` from the old `users` table;
- creates a v2 `members` row on the `discord` platform;
- links the GitHub username and uses the old points as the baseline;
- recalculates badges from points using the v2 thresholds;
- does **not** import `current_challenge` or `last_activity_check`;
- never resets an existing v2 link's points.

Caveats:

- Old `discord_id` values become `members.user_id`; display names are the Discord ID
  until the member speaks again.
- If two old Discord rows shared one GitHub username, v2 shares one link and keeps the
  existing score; the importer reports the merge.
- Old badges are not copied verbatim; they are derived from points. If you used custom
  badges in v1, you will need a small follow-up SQL update.
- Back up the target database first. The importer is idempotent for members/links but
  should still be treated as a one-time migration.

## What was removed

| v1 | v2 |
| --- | --- |
| `GEMINI_API_KEY` | `OLLAMA_*`, local model |
| `!set_gemini_model`, `!list_gemini_models` | Set `OLLAMA_MODEL` and restart; `/status` shows the model |
| `!sentiment <message_id>` | `!sentiment <text>` works across platforms without fetching message IDs |
| `!shutdown` for anyone | Admin-only, disabled by default, requires `confirm` |
| Discord-only commands | Discord slash commands + prefix commands on every adapter |
| One table | Versioned schema with members, links, ledger, settings |
| Points keyed by Discord ID | Points keyed by GitHub identity, shared across platforms |

`!set_repo`, `!link_github`, `!my_challenge`, `!leaderboard` and `!update_stats` still
work through aliases (`!set_repo`, `!link`, `!challenge`, `!leaderboard`, `!refresh`).

## Environment mapping

| v1 | v2 |
| --- | --- |
| `GEMINI_API_KEY` | remove |
| `GITHUB_TOKEN` | same |
| `DISCORD_BOT_TOKEN` | same |
| — | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |
| — | `DISCORD_ADMIN_IDS` (required for admin commands) |
| — | `BRIDGE_SHARED_SECRET` if using the bridge |
| — | `GITHUB_WEBHOOK_SECRET` if using webhooks |

## Rollback

Keep the v1 folder and `user_data.db` until the new deployment has run successfully for
a week. v2 never writes to `user_data.db`, so rollback is simply running the old code
again with v1's `.env`. New points earned in v2 will not appear in v1.
