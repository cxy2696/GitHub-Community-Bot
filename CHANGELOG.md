# Changelog

All notable changes are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned

- Slack slash commands through a signed HTTP endpoint.
- GitHub App authentication.
- Read-only admin status page.
- Adapter contract fixtures.
- More locales (Korean, Spanish, Portuguese).

## [2.1.0] — 2026-11-11

The website and demo release, published under the new repository name.

### Added

- **Static project website** served from `docs/` on GitHub Pages, with no build step,
  no external CDN and no analytics.
- **Interactive browser demo** with scripted English, 中文 and 日本語 replies, platform
  switching, command suggestions, a language selector and an explicit simulation
  notice.
- **README animation** (`docs/assets/demo.gif`), poster, and a 1200×630 Open Graph
  image so the project has a useful social preview.
- **Reproducible demo assets** via `scripts/render_demo_assets.py`, plus
  `make demo` and `make demo-assets` targets.
- **`docs/DEMO.md`** covering the demo, local serving, accessibility and GitHub Pages
  deployment.

### Changed

- Renamed the repository from `GitHub-Discord-Bot` to **`GitHub-Community-Bot`**;
  existing links redirect. Updated clone URLs, badges, issue templates, security
  advisory links, package metadata and documentation.
- Bumped the package to **2.1.0**.
- The website is now the repository homepage / live demo link.

## [2.0.0] — 2026-11-11

The platform-neutral, local-AI release. This is a ground-up rewrite of the original
Discord-only Gemini bot.

### Added

- **Ollama integration** (`POST /api/chat`) with model health checks, retries, typed
  errors, localized safety prompts and a bounded in-memory conversation history.
- **Six adapters:** Discord (slash + prefix + DMs), Slack (Socket Mode), Telegram
  (long polling + localized command menus), Matrix (unencrypted rooms), a signed HTTP
  bridge for any other chat app, and a terminal adapter.
- **English / 中文 / 日本語** UI, command aliases and documentation.
- **Shared GitHub identity:** points belong to the GitHub account, not a chat account;
  linking the same account from two platforms does not double history.
- **Idempotent activity ledger** with stable keys for commits, issues and pull requests.
- **GitHub webhooks** for `push`, `issues.opened` and `pull_request.opened`, with
  `X-Hub-Signature-256` verification; polling remains a backstop.
- **HTTP operations surface:** `/healthz`, `/readyz`, `/metrics`, `/version`.
- **Prometheus-style metrics** with no extra dependency.
- **Versioned SQLite schema** and automatic migrations.
- **Privacy controls:** `!privacy` inspection, opt-out/opt-in, DM-only confirmed
  deletion; orphaned scores and the activity ledger are removed with the last link.
- **Docker + Compose** with Ollama, a model-pull service, persistent volumes and a
  container health check.
- **systemd, reverse proxy, backup and operations documentation.**
- **CI** on Python 3.11–3.13 with Ruff and 60+ offline tests.
- **v1 importer** (`scripts/import_v1.py`) for communities that want to preserve their
  old Discord leaderboard.

### Changed

- Default AI model is now local `qwen2.5:3b`; no Gemini key or paid tier is required.
- Leaderboard rendering uses stored scores instead of one GitHub API call per member.
- GitHub totals are cached for five minutes and fall back to a paginated scan when the
  search API is rate-limited.
- Points, badges and thresholds are centralized in `models.py`.
- Admin commands require explicit per-platform allowlists.
- `!set_repo`, `!link`, `!challenge`, `!leaderboard` and `!refresh` replace the old
  command set while keeping familiar aliases.
- Tone reflection (`!sentiment`) no longer requires fetching a message by ID, which
  makes it usable on every platform.
- The project name in documentation is **GitHub Community Bot**.

### Removed

- `GEMINI_API_KEY`, Gemini model selection commands and all Gemini API calls.
- Public `!shutdown`; remote shutdown is now admin-only, confirmed and disabled by
  default.
- The single-table `user_data.db` schema and Discord-ID-keyed scores.
- Per-user GitHub API calls from the leaderboard path.
- The old `bot.py` monolith (available in Git history).

### Fixed

- Duplicate points when the same activity is seen by both polling and a webhook.
- Double-counted historical contributions when linking from multiple platforms.
- GitHub polling races that could skip activity created during a poll.
- Unbounded replies on long leaderboards and AI answers (adapters now chunk safely).
- Missing validation for repo names, ports, locales and platform credentials.
- Secrets appearing in logs (redaction filter added).
- Slow commands blocking the Discord heartbeat (GitHub calls run in worker threads).
- Global shutdown command exposed to every member.

### Security

- Bridge requests require HMAC-SHA256 and optionally a signed timestamp with a ±5
  minute replay window.
- GitHub webhook signatures are verified; the endpoint is disabled without a secret.
- Admin checks are computed by adapters from allowlists, never accepted from request
  payloads.
- Profile deletion requires a DM and an explicit confirmation.
- Logs redact GitHub, Slack, Telegram and bearer tokens.
- Docker runs as a non-root user with a persistent, least-privilege data volume.

### Migration notes

- v1 users must add an Ollama model and may drop `GEMINI_API_KEY`.
- Existing Discord/GitHub tokens continue to work.
- A fresh v2 database is recommended; `scripts/import_v1.py` optionally imports old
  points.
- See [docs/MIGRATION.md](docs/MIGRATION.md).

## [1.0.0] — 2025

Initial Discord bot with Gemini-generated challenges, sentiment analysis, points,
badges and a leaderboard. Archived in Git history.
