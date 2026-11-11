# Contributing

Thanks for considering a contribution. This project values small, well-tested
changes that make a self-hosted community bot easier to run and kinder to use.

## Ways to help

- Report a bug with a minimal reproduction and the relevant log lines (redact secrets).
- Improve documentation, including translations.
- Add a platform adapter or a test fixture.
- Review a pull request, especially its failure behavior.
- Try the bot with a real Ollama model and report quality issues.

## Development setup

```bash
git clone https://github.com/cxy2696/GitHub-Discord-Bot.git
cd GitHub-Discord-Bot
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Ollama is optional for tests. All tests are offline and use fakes.

```bash
make lint       # ruff check + format check
make test       # pytest
make check      # config validation without network
make run        # start the bot
```

Run the CLI without any platform credentials:

```bash
HTTP_ENABLED=false python -m github_community_bot --cli
```

## Before opening a pull request

- [ ] The change is focused and described in the PR template.
- [ ] `make lint` and `make test` pass.
- [ ] New behavior has a test (or a clear explanation of why a test is impossible).
- [ ] User-facing strings exist in `en`, `zh` and `ja`.
- [ ] No secrets, tokens, personal data or generated databases are included.
- [ ] Docs are updated if configuration, commands or deployment changed.
- [ ] The change does not add a mandatory paid service or a heavy dependency without
      prior discussion.

## Code style

- Python 3.11+, type hints on public functions, `from __future__ import annotations`.
- Async by default for I/O; never block the event loop in an adapter.
- Adapters translate and deliver. Business logic belongs in `CommunityBot` or a
  service, not in a platform module.
- Errors shown to users must be localized and actionable; technical details go to logs.
- Prefer a small dependency over a framework. Prefer the standard library over a small
  dependency.
- Keep comments about *why*, not *what*. The code should explain the what.

Ruff is the formatter and linter:

```bash
ruff format .
ruff check .
```

## Tests

```bash
pytest -q
pytest tests/test_bot.py -q
pytest -k privacy -q
```

Guidelines:

- No network in tests. Use a fake adapter/service or a temporary SQLite database.
- Test the failure path, not only the happy path.
- For storage, assert idempotency and shared-identity behavior.
- For HTTP, sign the exact bytes you send.
- Do not lower coverage by deleting a test that caught a real bug; fix the bug or
  document why the test is obsolete.

## Adding a command

1. Add a handler in `CommunityBot._handlers`.
2. Add translation keys to all three catalogs.
3. Add a help line and a localized alias if it makes sense.
4. Add a test in `tests/test_bot.py`.
5. Decide whether it is admin-only; check `message.is_admin`.
6. Decide whether it needs a DM; check `message.is_dm`.
7. Keep the response under ~1,500 characters where possible.

## Adding a platform

See [docs/PLATFORMS.md](docs/PLATFORMS.md#adding-a-new-adapter). A good adapter PR
includes normalization tests, a config block, docs, and an env example.

## Translations

Read [docs/TRANSLATIONS.md](docs/TRANSLATIONS.md). Machine translation is welcome as a
draft, but user-facing Chinese/Japanese changes need fluent review. Keep placeholders
and command names unchanged.

## Commit and PR style

- Use the imperative mood: `fix: preserve link score on duplicate webhook`.
- Conventional prefixes are welcome but not enforced: `feat`, `fix`, `docs`, `test`,
  `refactor`, `chore`.
- One logical change per PR. Refactors that touch everything are hard to review.
- Describe the user-visible effect and the failure mode you considered.

## AI-assisted contributions

AI assistance is allowed. You remain responsible for correctness, licensing, tests and
security. Do not paste secrets or private community data into a model. If a substantial
part of a change was generated, say so in the PR so reviewers can focus.

## Security

Do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md).

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be kind,
assume good intent, and critique the work rather than the person.
