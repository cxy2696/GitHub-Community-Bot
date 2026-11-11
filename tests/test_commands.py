from __future__ import annotations

from github_community_bot.commands import (
    normalize_command,
    parse_command,
    strip_bot_mention,
)


def test_parse_english_aliases():
    parsed = parse_command("!my_challenge", ("!", "/"))
    assert parsed is not None
    assert parsed.name == "challenge"


def test_parse_chinese_and_japanese():
    assert parse_command("!帮助", ("!",)).name == "help"
    assert parse_command("!ランキング", ("!",)).name == "leaderboard"
    assert parse_command("!绑定 alice", ("!",)).args == "alice"


def test_parse_telegram_suffix():
    parsed = parse_command("/help@MyBot", ("/",))
    assert parsed is not None and parsed.name == "help"


def test_parse_unknown_and_non_command():
    assert parse_command("hello", ("!",)) is None
    assert parse_command("!", ("!",)) is None
    assert normalize_command("set-repo") == "set_repo"
    assert normalize_command("nonsense") is None


def test_strip_mention():
    text, mentioned = strip_bot_mention("<@123> help", "123")
    assert text == "help" and mentioned is True
    text, mentioned = strip_bot_mention("hello", "123")
    assert text == "hello" and mentioned is False
    text, mentioned = strip_bot_mention("<@456> hello", "123")
    assert text == "hello" and mentioned is True
