"""Application wiring: build services, start adapters, wait for shutdown."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from collections.abc import Sequence

from . import __version__
from .bot import CommunityBot
from .config import AppConfig, ConfigError, load_config
from .i18n import I18n
from .logging_setup import setup_logging
from .metrics import Metrics
from .platforms.base import PlatformAdapter
from .services.ai import OllamaClient
from .services.github import GitHubService
from .storage import Database

logger = logging.getLogger(__name__)


def build_adapters(config: AppConfig, cli: bool = False) -> list[PlatformAdapter]:
    adapters: list[PlatformAdapter] = []

    if config.discord.enabled:
        from .platforms.discord import DiscordAdapter

        adapters.append(DiscordAdapter(config.discord))
    if config.slack.enabled:
        from .platforms.slack import SlackAdapter

        adapters.append(SlackAdapter(config.slack))
    if config.telegram.enabled:
        from .platforms.telegram import TelegramAdapter

        adapters.append(TelegramAdapter(config.telegram))
    if config.matrix.enabled:
        from .platforms.matrix import MatrixAdapter

        adapters.append(MatrixAdapter(config.matrix))
    if config.http.enabled:
        from .platforms.http_server import HTTPServerAdapter

        adapters.append(HTTPServerAdapter(config.http))
    if cli:
        from .platforms.cli import CLIAdapter

        adapters.append(CLIAdapter())
    return adapters


async def run(config: AppConfig, cli: bool = False) -> int:
    database = Database(config.database_path)
    i18n = I18n()
    ai = OllamaClient(config.ollama)
    github = GitHubService(config.github)
    metrics = Metrics()
    bot = CommunityBot(config, database, i18n, ai, github, metrics)
    adapters = build_adapters(config, cli=cli)

    if not adapters:
        logger.error(
            "No adapters are enabled. Set a platform token, enable HTTP for the web "
            "bridge, or run with --cli for a local demo."
        )
        return 2

    for adapter in adapters:
        bot.register_adapter(adapter.name, adapter)

    await bot.start()
    started: list[PlatformAdapter] = []
    try:
        for adapter in adapters:
            try:
                await adapter.start(bot)
                started.append(adapter)
                logger.info("Adapter %s started", adapter.name)
            except Exception:
                logger.exception("Could not start the %s adapter", adapter.name)
                bot.metrics.inc("bot_adapter_start_errors_total", adapter=adapter.name)

        if not started:
            logger.error("No adapters could be started; shutting down.")
            return 1

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, bot.shutdown_event.set)

        logger.info("Ready. Press Ctrl+C or send an admin shutdown command to stop.")
        await bot.shutdown_event.wait()
        return 0
    finally:
        for adapter in reversed(started):
            try:
                await adapter.stop()
            except Exception:
                logger.exception("Error while stopping adapter %s", adapter.name)
        await bot.stop()


def _check(config: AppConfig) -> int:
    platforms = ", ".join(config.enabled_platforms()) or "none (use --cli)"
    print(f"{config.bot_name} v{__version__}")
    print(f"Configuration valid. Platforms: {platforms}")
    print(f"Database: {config.database_path}")
    print(f"Ollama: {config.ollama.base_url} · model {config.ollama.model}")
    print(f"GitHub repo: {config.github.repo or 'not selected yet'}")
    print(f"Locales: en, zh, ja · default {config.default_locale}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-community-bot",
        description="Free, open-source, multi-platform GitHub community bot with local Ollama AI.",
    )
    parser.add_argument("--cli", action="store_true", help="add an interactive terminal adapter")
    parser.add_argument("--check", action="store_true", help="validate configuration and exit")
    parser.add_argument("--env-file", default=".env", help="path to an optional .env file")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.env_file)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Could not load configuration: {exc}", file=sys.stderr)
        return 2

    setup_logging(config.log_level, config.log_format)
    if args.check:
        return _check(config)

    try:
        return asyncio.run(run(config, cli=args.cli))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
