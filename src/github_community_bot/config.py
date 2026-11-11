"""Configuration loading and validation.

The bot is configured entirely through environment variables (and an optional
``.env`` file) so that it behaves the same locally, in Docker, and on a PaaS.
Every value is validated once at startup; a bad value fails fast with an
actionable message instead of surfacing later as a confusing runtime error.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

SUPPORTED_LOCALES = ("en", "zh", "ja")
LOCALE_LABELS = {"en": "English", "zh": "中文", "ja": "日本語"}
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_TRUE = {"1", "true", "yes", "on", "y"}
_FALSE = {"0", "false", "no", "off", "n"}


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


def _raw(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _bool(name: str, default: bool) -> bool:
    raw = _raw(name)
    if raw is None:
        return default
    if raw.lower() in _TRUE:
        return True
    if raw.lower() in _FALSE:
        return False
    raise ConfigError(f"{name} must be a boolean (true/false), got {raw!r}")


def _optional_bool(name: str) -> bool | None:
    raw = _raw(name)
    if raw is None:
        return None
    return _bool(name, False)


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = _raw(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def _float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = _raw(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def _csv(name: str) -> frozenset[str]:
    raw = _raw(name)
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _csv_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _raw(name)
    if not raw:
        return default
    values = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    return values or default


def _url(name: str, default: str) -> str:
    raw = _raw(name, default) or default
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{name} must be an http(s) URL, got {raw!r}")
    return raw.rstrip("/")


def _locale(name: str, default: str) -> str:
    raw = (_raw(name, default) or default).lower()
    primary = raw.replace("_", "-").split("-")[0]
    if primary not in SUPPORTED_LOCALES:
        raise ConfigError(
            f"{name} must be one of {', '.join(SUPPORTED_LOCALES)} (or a locale such as zh-CN), "
            f"got {raw!r}"
        )
    return primary


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    enabled: bool = True
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:3b"
    timeout_seconds: float = 60.0
    keep_alive: str = "10m"
    temperature: float = 0.6
    max_tokens: int = 512
    health_cache_seconds: int = 30


@dataclass(frozen=True, slots=True)
class GitHubConfig:
    token: str | None = None
    repo: str | None = None
    api_url: str = "https://api.github.com"
    poll_interval_seconds: int = 300
    webhook_secret: str | None = None
    request_timeout_seconds: int = 30


@dataclass(frozen=True, slots=True)
class HttpConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    max_body_bytes: int = 1_048_576
    bridge_secret: str | None = None
    trust_proxy_headers: bool = False


@dataclass(frozen=True, slots=True)
class DiscordConfig:
    enabled: bool = False
    token: str | None = None
    admin_ids: frozenset[str] = field(default_factory=frozenset)
    channel_ids: frozenset[str] = field(default_factory=frozenset)
    sync_commands: bool = True
    command_prefix: str = "!"


@dataclass(frozen=True, slots=True)
class SlackConfig:
    enabled: bool = False
    bot_token: str | None = None
    app_token: str | None = None
    admin_ids: frozenset[str] = field(default_factory=frozenset)
    channel_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    enabled: bool = False
    token: str | None = None
    admin_ids: frozenset[str] = field(default_factory=frozenset)
    chat_ids: frozenset[str] = field(default_factory=frozenset)
    api_base: str = "https://api.telegram.org"


@dataclass(frozen=True, slots=True)
class MatrixConfig:
    enabled: bool = False
    homeserver: str | None = None
    user_id: str | None = None
    access_token: str | None = None
    admin_ids: frozenset[str] = field(default_factory=frozenset)
    room_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    admin_ids: frozenset[str] = field(default_factory=frozenset)
    platform_name: str = "bridge"


@dataclass(frozen=True, slots=True)
class Limits:
    rate_limit_per_minute: int = 30
    max_ai_input_chars: int = 2000
    max_context_messages: int = 6
    leaderboard_size: int = 10
    retention_days: int = 365


@dataclass(frozen=True, slots=True)
class AppConfig:
    bot_name: str = "GitHub Community Bot"
    default_locale: str = "en"
    data_dir: Path = Path("data")
    database_path: Path = Path("data/community.db")
    log_level: str = "INFO"
    log_format: str = "text"
    command_prefixes: tuple[str, ...] = ("!", "/")
    allow_remote_shutdown: bool = False
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    http: HttpConfig = field(default_factory=HttpConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    matrix: MatrixConfig = field(default_factory=MatrixConfig)
    bridge: BridgeConfig = field(default_factory=BridgeConfig)
    limits: Limits = field(default_factory=Limits)

    def enabled_platforms(self) -> tuple[str, ...]:
        platforms = []
        if self.discord.enabled:
            platforms.append("discord")
        if self.slack.enabled:
            platforms.append("slack")
        if self.telegram.enabled:
            platforms.append("telegram")
        if self.matrix.enabled:
            platforms.append("matrix")
        if self.http.enabled:
            platforms.append("http")
        return tuple(platforms)

    def validate(self) -> None:
        if self.github.repo and not REPO_PATTERN.fullmatch(self.github.repo):
            raise ConfigError(
                f"GITHUB_REPO must look like owner/repository, got {self.github.repo!r}"
            )
        if self.discord.enabled and not self.discord.token:
            raise ConfigError("Discord is enabled but DISCORD_BOT_TOKEN is empty")
        if self.slack.enabled and not (self.slack.bot_token and self.slack.app_token):
            raise ConfigError(
                "Slack is enabled but SLACK_BOT_TOKEN and/or SLACK_APP_TOKEN is empty"
            )
        if self.telegram.enabled and not self.telegram.token:
            raise ConfigError("Telegram is enabled but TELEGRAM_BOT_TOKEN is empty")
        if self.matrix.enabled and not (
            self.matrix.homeserver and self.matrix.user_id and self.matrix.access_token
        ):
            raise ConfigError(
                "Matrix is enabled but MATRIX_HOMESERVER, MATRIX_USER_ID and "
                "MATRIX_ACCESS_TOKEN must all be set"
            )
        if self.http.enabled and not (1 <= self.http.port <= 65535):
            raise ConfigError("HTTP_PORT must be between 1 and 65535")
        if not self.command_prefixes:
            raise ConfigError("COMMAND_PREFIXES must contain at least one prefix")
        if self.github.repo and not self.github.token:
            # Public repositories can be read anonymously; make the trade-off visible.
            pass


def load_config(env_file: str | Path | None = ".env") -> AppConfig:
    """Load configuration from ``.env`` and the process environment."""

    if env_file is not None:
        load_dotenv(dotenv_path=env_file, override=False)

    data_dir = Path(_raw("DATA_DIR", "data") or "data").expanduser()
    database_path = Path(
        _raw("DATABASE_PATH", str(data_dir / "community.db")) or data_dir / "community.db"
    ).expanduser()

    discord_token = _raw("DISCORD_BOT_TOKEN")
    discord_enabled = _optional_bool("DISCORD_ENABLED")
    if discord_enabled is None:
        discord_enabled = bool(discord_token)

    telegram_token = _raw("TELEGRAM_BOT_TOKEN")
    telegram_enabled = _optional_bool("TELEGRAM_ENABLED")
    if telegram_enabled is None:
        telegram_enabled = bool(telegram_token)

    slack_bot_token = _raw("SLACK_BOT_TOKEN")
    slack_app_token = _raw("SLACK_APP_TOKEN")
    slack_enabled = _optional_bool("SLACK_ENABLED")
    if slack_enabled is None:
        slack_enabled = bool(slack_bot_token and slack_app_token)

    matrix_homeserver = _raw("MATRIX_HOMESERVER")
    matrix_user_id = _raw("MATRIX_USER_ID")
    matrix_access_token = _raw("MATRIX_ACCESS_TOKEN")
    matrix_enabled = _optional_bool("MATRIX_ENABLED")
    if matrix_enabled is None:
        matrix_enabled = bool(matrix_homeserver and matrix_user_id and matrix_access_token)

    config = AppConfig(
        bot_name=_raw("BOT_NAME", "GitHub Community Bot") or "GitHub Community Bot",
        default_locale=_locale("DEFAULT_LOCALE", "en"),
        data_dir=data_dir,
        database_path=database_path,
        log_level=(_raw("LOG_LEVEL", "INFO") or "INFO").upper(),
        log_format=(_raw("LOG_FORMAT", "text") or "text").lower(),
        command_prefixes=_csv_tuple("COMMAND_PREFIXES", ("!", "/")),
        allow_remote_shutdown=_bool("ALLOW_REMOTE_SHUTDOWN", False),
        ollama=OllamaConfig(
            enabled=_bool("OLLAMA_ENABLED", True),
            base_url=_url("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            model=_raw("OLLAMA_MODEL", "qwen2.5:3b") or "qwen2.5:3b",
            timeout_seconds=_float("OLLAMA_TIMEOUT_SECONDS", 60.0, 5.0, 600.0),
            keep_alive=_raw("OLLAMA_KEEP_ALIVE", "10m") or "10m",
            temperature=_float("OLLAMA_TEMPERATURE", 0.6, 0.0, 2.0),
            max_tokens=_int("OLLAMA_MAX_TOKENS", 512, 64, 8192),
            health_cache_seconds=_int("OLLAMA_HEALTH_CACHE_SECONDS", 30, 5, 600),
        ),
        github=GitHubConfig(
            token=_raw("GITHUB_TOKEN"),
            repo=_raw("GITHUB_REPO"),
            api_url=_url("GITHUB_API_URL", "https://api.github.com"),
            poll_interval_seconds=_int("GITHUB_POLL_INTERVAL_SECONDS", 300, 60, 86_400),
            webhook_secret=_raw("GITHUB_WEBHOOK_SECRET"),
            request_timeout_seconds=_int("GITHUB_REQUEST_TIMEOUT_SECONDS", 30, 5, 300),
        ),
        http=HttpConfig(
            enabled=_bool("HTTP_ENABLED", True),
            host=_raw("HTTP_HOST", "0.0.0.0") or "0.0.0.0",
            port=_int("HTTP_PORT", 8080, 1, 65535),
            max_body_bytes=_int("HTTP_MAX_BODY_BYTES", 1_048_576, 4096, 16_777_216),
            bridge_secret=_raw("BRIDGE_SHARED_SECRET"),
            trust_proxy_headers=_bool("TRUST_PROXY_HEADERS", False),
        ),
        discord=DiscordConfig(
            enabled=discord_enabled,
            token=discord_token,
            admin_ids=_csv("DISCORD_ADMIN_IDS"),
            channel_ids=_csv("DISCORD_CHANNEL_IDS"),
            sync_commands=_bool("DISCORD_SYNC_COMMANDS", True),
            command_prefix=(_raw("DISCORD_COMMAND_PREFIX", "!") or "!"),
        ),
        slack=SlackConfig(
            enabled=slack_enabled,
            bot_token=slack_bot_token,
            app_token=slack_app_token,
            admin_ids=_csv("SLACK_ADMIN_IDS"),
            channel_ids=_csv("SLACK_CHANNEL_IDS"),
        ),
        telegram=TelegramConfig(
            enabled=telegram_enabled,
            token=telegram_token,
            admin_ids=_csv("TELEGRAM_ADMIN_IDS"),
            chat_ids=_csv("TELEGRAM_CHAT_IDS"),
            api_base=_url("TELEGRAM_API_BASE", "https://api.telegram.org"),
        ),
        matrix=MatrixConfig(
            enabled=matrix_enabled,
            homeserver=matrix_homeserver.rstrip("/") if matrix_homeserver else None,
            user_id=matrix_user_id,
            access_token=matrix_access_token,
            admin_ids=_csv("MATRIX_ADMIN_IDS"),
            room_ids=_csv("MATRIX_ROOM_IDS"),
        ),
        bridge=BridgeConfig(
            admin_ids=_csv("BRIDGE_ADMIN_IDS"),
            platform_name=_raw("BRIDGE_PLATFORM_NAME", "bridge") or "bridge",
        ),
        limits=Limits(
            rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 30, 1, 600),
            max_ai_input_chars=_int("MAX_AI_INPUT_CHARS", 2000, 100, 20_000),
            max_context_messages=_int("MAX_CONTEXT_MESSAGES", 6, 0, 20),
            leaderboard_size=_int("LEADERBOARD_SIZE", 10, 3, 50),
            retention_days=_int("RETENTION_DAYS", 365, 7, 3650),
        ),
    )

    if config.log_format not in {"text", "json"}:
        raise ConfigError("LOG_FORMAT must be 'text' or 'json'")
    if config.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")
    config.validate()
    return config
