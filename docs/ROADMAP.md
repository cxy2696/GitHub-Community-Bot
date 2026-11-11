# Roadmap

This is a living plan, not a promise. Priorities are chosen to keep the project small,
self-hostable and maintainable by a small group of volunteers.

## Now — v2.0 (shipped)

- Ollama local AI with typed failures and deterministic fallbacks
- Discord, Slack, Telegram, Matrix, HTTP bridge and CLI adapters
- English / 中文 / 日本語 UI and command aliases
- Shared GitHub identity, versioned SQLite schema, idempotent activity ledger
- GitHub webhooks and polling with deduplication
- Health, readiness, Prometheus metrics, Docker, systemd guidance, backups
- CI on Python 3.11–3.13 with 60+ offline tests

## Next — v2.1 (maintenance and polish)

- **Slack slash commands** via a signed HTTP endpoint, so `/ask` works without a
  mention. Socket Mode already covers mentions and DMs.
- **GitHub App authentication** as an alternative to personal access tokens, with
  installation tokens and finer permissions.
- **Admin web page** (read-only status and a “refresh now” button) behind the existing
  admin allowlist, with CSRF protection.
- **Adapter contract tests** with recorded fixtures for Discord/Slack/Telegram
  payloads.
- **Structured audit events** for admin actions (set repo, unlink, delete) in a
  separate table with retention.
- **Better first-run onboarding**: a `/setup` checklist and a clear “no repo selected”
  hint in `/status`.
- **Model recommendations by hardware** in the docs, including a tiny 1.5B profile.

## Later — explore

- Optional PostgreSQL storage for communities that outgrow SQLite.
- Matrix E2EE via a dedicated crypto-capable client, or a documented bridge to one.
- GitHub issue/PR review *quality* signals (carefully, without gamifying review count).
- Weekly digest messages to an opt-in channel.
- Per-channel repository selection for multi-project servers.
- More locales: Korean, Spanish, Portuguese, German, French.
- A small theme/translation contribution guide with screenshots.

## Explicitly not planned

- Storing or indexing chat history.
- Automatic moderation, sentiment-based punishment, or “toxic user” scores.
- Paid AI APIs as a default dependency.
- A hosted SaaS with one shared database for unrelated communities.
- Engagement mechanics that reward volume over kindness (for example, points for
  comment count).

## How to influence the roadmap

Open an issue with the `enhancement` label and describe:

1. the community problem, not only the feature;
2. who benefits and how often;
3. the smallest version that would help;
4. operational cost (new service, new secret, new permission);
5. whether you can help test or implement.

Roadmap items that add a database, a queue, a cloud dependency or a new permission are
held to a higher bar. The project's advantage is that one person can run it.

## Release policy

- `MAJOR`: schema-breaking changes, removed adapters, changed command semantics.
- `MINOR`: new adapters, commands, locales, optional integrations.
- `PATCH`: fixes, documentation, dependency updates without behavior changes.

Tags use `vX.Y.Z`. `CHANGELOG.md` is updated before tagging. Migrations are additive
within a major version; back up before any upgrade.
