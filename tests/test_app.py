from __future__ import annotations

import sqlite3

from github_community_bot.app import build_adapters
from github_community_bot.config import (
    AppConfig,
    DiscordConfig,
    HttpConfig,
    SlackConfig,
    TelegramConfig,
)


def test_build_adapters_only_enables_configured_platforms():
    config = AppConfig(
        http=HttpConfig(enabled=False),
        discord=DiscordConfig(enabled=True, token="x"),
        telegram=TelegramConfig(enabled=True, token="y"),
        slack=SlackConfig(enabled=False),
    )
    adapters = build_adapters(config, cli=True)
    assert [adapter.name for adapter in adapters] == ["discord", "telegram", "cli"]


def test_build_adapters_can_return_none():
    config = AppConfig(http=HttpConfig(enabled=False))
    assert build_adapters(config, cli=False) == []


def test_check_command(capsys, monkeypatch):
    monkeypatch.setenv("HTTP_ENABLED", "false")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("MATRIX_HOMESERVER", raising=False)
    from github_community_bot.app import main

    assert main(["--check", "--env-file", "/dev/null"]) == 0
    assert "Configuration valid" in capsys.readouterr().out


def test_v1_import(tmp_path):
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))
    import import_v1

    legacy = tmp_path / "user_data.db"
    connection = sqlite3.connect(legacy)
    connection.execute(
        "CREATE TABLE users (discord_id TEXT PRIMARY KEY, github_user TEXT, points INTEGER,"
        " badges TEXT, current_challenge TEXT, last_activity_check TEXT)"
    )
    connection.execute("INSERT INTO users VALUES ('111', 'alice', 120, '[]', NULL, NULL)")
    connection.execute("INSERT INTO users VALUES ('222', 'alice', 700, '[]', NULL, NULL)")
    connection.commit()
    connection.close()

    rows = import_v1.read_legacy(legacy)
    assert len(rows) == 2

    import asyncio

    target = tmp_path / "community.db"
    stats = asyncio.run(import_v1.import_rows(rows, target, "discord"))
    assert stats["members"] == 2
    assert stats["new_links"] == 1
    assert stats["merged_links"] == 1

    from github_community_bot.storage import Database

    async def inspect():
        db = Database(target)
        await db.connect()
        try:
            link = await db.get_link("alice")
            assert link is not None
            assert link.points == 700
            assert "silver" in link.badges
        finally:
            await db.close()

    asyncio.run(inspect())
