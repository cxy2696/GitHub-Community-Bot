# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 2.x | Yes |
| 1.x (legacy `bot.py`) | No; upgrade |

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private vulnerability reporting:

<https://github.com/cxy2696/GitHub-Community-Bot/security/advisories/new>

Include:

- affected version/commit;
- deployment shape (platforms, public bridge/webhook or not);
- reproduction steps or a proof of concept;
- impact and any known mitigation;
- whether you want credit.

You should receive an acknowledgement within a few days. This is a volunteer project;
please allow reasonable time for a fix and coordinated disclosure.

## In scope

- Authentication/authorization bypass in admin commands or the bridge.
- HMAC/signature verification flaws in the bridge or GitHub webhook.
- Secret leakage through logs, errors, metrics or the repository.
- SQL injection or unsafe deserialization.
- Cross-platform data exposure (one member seeing another's private data).
- Denial of service through a single unauthenticated request.
- Dependency vulnerabilities with a realistic exploit path.

## Out of scope

- Vulnerabilities in Discord, Slack, Telegram, Matrix, GitHub or Ollama themselves
  (report them upstream).
- Misconfiguration such as exposing the bridge without TLS or publishing `/metrics`.
- Spam from a compromised platform account that the rate limiter cannot prevent.
- Social engineering of community admins.
- Findings that require an attacker to already control the host or the `.env` file.

## Deployment hardening

- Keep `.env` at mode `600`, owned by the service user, outside the web root.
- Set `BRIDGE_SHARED_SECRET` to a random 32-byte value. The bridge is disabled if unset.
- Set `GITHUB_WEBHOOK_SECRET` and use HTTPS for the webhook URL.
- Put the HTTP server behind TLS; expose only `/api/v1/*` and `/healthz` publicly.
- Do not publish `/metrics` to the internet; it reveals operational counts.
- Use `ALLOW_REMOTE_SHUTDOWN=false` (default).
- Grant GitHub tokens the least privilege: read-only Contents/Issues/PRs/Metadata.
- Use a dedicated Discord/Slack/Telegram/Matrix account for the bot.
- Rotate credentials after any suspected exposure and review logs.
- Back up the database and keep backups encrypted if they contain personal data.
- Run the container as the non-root user provided by the Dockerfile.

## Dependency updates

Dependabot is configured for pip and GitHub Actions. CI runs on every PR. Security
updates should be prioritized, tested and released as a patch. If a transitive
dependency is vulnerable and no fix exists, document the mitigation in the advisory.

## Log redaction

The logging formatter redacts common GitHub, Slack, Telegram and bearer tokens. This is
defense in depth. Do not deliberately log secrets; redaction can miss new formats.
