from __future__ import annotations

import os

import pytest

from github_community_bot.config import ConfigError, load_config

_MANAGED_PREFIXES = (
    "BOT_",
    "DISCORD_",
    "SLACK_",
    "TELEGRAM_",
    "MATRIX_",
    "GITHUB_",
    "OLLAMA_",
    "HTTP_",
    "BRIDGE_",
    "RATE_",
    "MAX_",
    "LEADERBOARD_",
    "RETENTION_",
    "DATA_DIR",
    "DATABASE_PATH",
    "DEFAULT_LOCALE",
    "LOG_",
    "COMMAND_",
    "ALLOW_",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for key in list(os.environ):
        if key.startswith(_MANAGED_PREFIXES):
            monkeypatch.delenv(key, raising=False)


def test_defaults_are_valid():
    config = load_config(env_file=None)
    assert config.default_locale == "en"
    assert config.ollama.model == "qwen2.5:3b"
    assert config.command_prefixes == ("!", "/")
    assert config.http.enabled is True
    assert "http" in config.enabled_platforms()


def test_platforms_auto_enable_from_tokens(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    config = load_config(env_file=None)
    assert config.discord.enabled is True
    assert config.telegram.enabled is True
    assert "discord" in config.enabled_platforms()
    assert "telegram" in config.enabled_platforms()


def test_explicit_disable_wins(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-token")
    monkeypatch.setenv("DISCORD_ENABLED", "false")
    config = load_config(env_file=None)
    assert config.discord.enabled is False


def test_invalid_locale(monkeypatch):
    monkeypatch.setenv("DEFAULT_LOCALE", "de")
    with pytest.raises(ConfigError, match="DEFAULT_LOCALE"):
        load_config(env_file=None)


def test_invalid_repo(monkeypatch):
    monkeypatch.setenv("GITHUB_REPO", "not-a-repo")
    with pytest.raises(ConfigError, match="owner/repository"):
        load_config(env_file=None)


def test_invalid_port(monkeypatch):
    monkeypatch.setenv("HTTP_PORT", "70000")
    with pytest.raises(ConfigError, match="HTTP_PORT"):
        load_config(env_file=None)


def test_missing_platform_secret(monkeypatch):
    monkeypatch.setenv("MATRIX_ENABLED", "true")
    monkeypatch.setenv("MATRIX_HOMESERVER", "https://matrix.example.org")
    with pytest.raises(ConfigError, match="MATRIX"):
        load_config(env_file=None)
