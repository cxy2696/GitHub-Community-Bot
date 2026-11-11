"""The platform-neutral brain of the bot.

Adapters only translate messages in and replies out. Everything else — command
handling, localisation, GitHub activity, points, privacy and health — lives
here, which keeps adding a new chat platform small and predictable.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from . import __version__
from .commands import normalize_command, parse_command
from .config import LOCALE_LABELS, REPO_PATTERN, SUPPORTED_LOCALES, AppConfig
from .gamification import format_badges, points_for
from .i18n import I18n, normalize_locale, resolve_locale
from .metrics import Metrics
from .models import ActivityItem, IncomingMessage, Member, Reply, ServiceHealth
from .services.ai import AIError, ConversationMemory, OllamaClient
from .services.github import GitHubError, GitHubService
from .storage import Database, LinkConflict

logger = logging.getLogger(__name__)

GITHUB_USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


class RateLimiter:
    """A small sliding-window limiter with no external dependencies."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        bucket = self._hits[key]
        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.limit:
            retry_after = max(1, int(self.window - (now - bucket[0])) + 1)
            return False, retry_after
        bucket.append(now)
        if len(self._hits) > 5000:
            self._prune(cutoff)
        return True, 0

    def _prune(self, cutoff: float) -> None:
        for key in list(self._hits):
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                self._hits.pop(key, None)


class CommunityBot:
    def __init__(
        self,
        config: AppConfig,
        database: Database,
        i18n: I18n,
        ai: OllamaClient,
        github: GitHubService,
        metrics: Metrics | None = None,
    ) -> None:
        self.config = config
        self.db = database
        self.i18n = i18n
        self.ai = ai
        self.github = github
        self.metrics = metrics or Metrics()
        self.memory = ConversationMemory(
            max_messages=config.limits.max_context_messages,
        )
        self.rate_limiter = RateLimiter(config.limits.rate_limit_per_minute)
        self.adapters: dict[str, Any] = {}
        self.started_at = time.time()
        self.shutdown_event = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._poll_lock = asyncio.Lock()
        self._closing = False
        self.last_poll_at: datetime | None = None
        self.last_poll_result: dict[str, int] = {}
        self._prefix = config.command_prefixes[0]
        self._handlers: dict[
            str, Callable[[IncomingMessage, Member, str, str], Awaitable[list[Reply]]]
        ] = {
            "help": self._cmd_help,
            "start": self._cmd_start,
            "about": self._cmd_about,
            "status": self._cmd_status,
            "language": self._cmd_language,
            "link": self._cmd_link,
            "challenge": self._cmd_challenge,
            "leaderboard": self._cmd_leaderboard,
            "sentiment": self._cmd_sentiment,
            "ask": self._cmd_ask,
            "privacy": self._cmd_privacy,
            "set_repo": self._cmd_set_repo,
            "refresh": self._cmd_refresh,
            "unlink": self._cmd_unlink,
            "shutdown": self._cmd_shutdown,
        }

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        await self.db.connect()
        await self.ai.start()
        await self._restore_repo()
        await self.db.prune_events(self.config.limits.retention_days)
        self._spawn(self._poll_loop())
        self._spawn(self._maintenance_loop())
        logger.info(
            "Core started (platforms=%s, repo=%s, model=%s)",
            ", ".join(self.config.enabled_platforms()) or "none",
            self.github.repo_name or "none",
            self.config.ollama.model,
        )

    async def stop(self) -> None:
        self._closing = True
        self.shutdown_event.set()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.ai.close()
        await self.github.close()
        await self.db.close()
        logger.info("Core stopped")

    def _spawn(self, coro: Awaitable[Any]) -> None:
        task = asyncio.create_task(coro)  # type: ignore[arg-type]
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "Background task failed: %s",
                error,
                exc_info=(type(error), error, error.__traceback__),
            )

    def register_adapter(self, name: str, adapter: Any) -> None:
        self.adapters[name] = adapter

    def adapter_states(self) -> dict[str, bool]:
        return {
            name: bool(getattr(adapter, "ready", False)) for name, adapter in self.adapters.items()
        }

    async def _restore_repo(self) -> None:
        stored = await self.db.get_setting("github_repo")
        repo_name = stored or self.config.github.repo
        if not repo_name:
            return
        try:
            info = await self.github.select_repo(repo_name)
            await self.db.set_setting("github_repo", info.full_name)
            logger.info("Tracking repository %s", info.full_name)
        except GitHubError as exc:
            logger.warning("Could not load repository %s at startup: %s", repo_name, exc)

    # ---------------------------------------------------------------- health

    async def health_report(self, include_external: bool = True) -> list[ServiceHealth]:
        checks: list[ServiceHealth] = []
        db_ok = await self.db.ping()
        checks.append(
            ServiceHealth("database", "online" if db_ok else "offline", str(self.db.path))
        )

        if include_external:
            ai_status, ai_detail = await self.ai.health()
            checks.append(ServiceHealth("ollama", ai_status, ai_detail))

            if not self.config.github.repo and not self.github.repo_name:
                checks.append(ServiceHealth("github", "not_configured", "No repository selected"))
            else:
                try:
                    status, detail = await asyncio.wait_for(self.github.health(), timeout=8)
                except (TimeoutError, GitHubError) as exc:
                    status, detail = "degraded", str(exc)[:160]
                checks.append(ServiceHealth("github", status, detail))
        else:
            checks.append(ServiceHealth("ollama", "unknown", "not checked"))
            checks.append(ServiceHealth("github", "unknown", "not checked"))

        for name, ready in self.adapter_states().items():
            checks.append(ServiceHealth(f"adapter:{name}", "online" if ready else "offline"))
        return checks

    async def readiness(self) -> tuple[bool, dict[str, Any]]:
        db_ok = await self.db.ping()
        adapters = self.adapter_states()
        ready = db_ok and (not adapters or any(adapters.values()))
        return ready, {
            "ready": ready,
            "database": db_ok,
            "adapters": adapters,
            "repo": self.github.repo_name,
            "model": self.config.ollama.model,
            "uptime_seconds": int(time.time() - self.started_at),
        }

    # ---------------------------------------------------------------- messages

    async def handle_message(self, message: IncomingMessage) -> list[Reply]:
        self.metrics.inc("bot_messages_total", platform=message.platform)
        started = time.perf_counter()
        member: Member | None = None
        locale = resolve_locale(None, message.locale_hint, message.text, self.config.default_locale)
        try:
            member = await self.db.touch_member(
                message.platform,
                message.user_id,
                message.user_name,
                normalize_locale(message.locale_hint),
            )
            locale = resolve_locale(
                member.locale, message.locale_hint, message.text, self.config.default_locale
            )

            allowed, retry_after = self.rate_limiter.check(message.user_key)
            if not allowed and not message.is_admin:
                self.metrics.inc("bot_rate_limited_total", platform=message.platform)
                return [Reply(self.i18n.t("error.rate_limited", locale, seconds=retry_after))]

            command = parse_command(message.text, self.config.command_prefixes)
            if command is None and (message.mentions_bot or message.is_dm):
                # ``@bot help`` and a DM containing just ``help`` should feel
                # like commands, not like an AI question.
                first = message.text.strip().split(maxsplit=1)[0] if message.text.strip() else ""
                if normalize_command(first):
                    command = parse_command(
                        f"{self._prefix}{message.text.strip()}",
                        self.config.command_prefixes,
                    )
            if command is not None:
                if command.name not in self._handlers:
                    self.metrics.inc(
                        "bot_commands_total", command="unknown", platform=message.platform
                    )
                    return [
                        Reply(
                            self.i18n.t(
                                "error.unknown_command",
                                locale,
                                command=command.name,
                                prefix=self._prefix,
                            )
                        )
                    ]

                if member.opted_out and command.name not in {"privacy", "help"}:
                    return [Reply(self.i18n.t("privacy.opted_out", locale, prefix=self._prefix))]

                self.metrics.inc(
                    "bot_commands_total", command=command.name, platform=message.platform
                )
                handler = self._handlers[command.name]
                return await handler(message, member, command.args, locale)

            if member.opted_out:
                return []

            if message.mentions_bot or message.is_dm:
                return await self._chat(message, member, locale)

            return []
        except Exception:
            logger.exception("Unhandled error for %s/%s", message.platform, message.user_id)
            self.metrics.inc("bot_errors_total", where="handle_message")
            return [Reply(self.i18n.t("error.generic", locale))]
        finally:
            self.metrics.inc(
                "bot_message_latency_seconds_sum",
                time.perf_counter() - started,
                platform=message.platform,
            )
            self.metrics.inc("bot_message_latency_seconds_count", platform=message.platform)

    # ------------------------------------------------------------------ commands

    async def _cmd_help(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        parts = [
            self.i18n.t("help.title", locale, bot_name=self.config.bot_name),
            self.i18n.t("help.body", locale, prefix=self._prefix),
        ]
        if message.is_admin:
            parts.append(self.i18n.t("help.admin", locale, prefix=self._prefix))
        parts.append(self.i18n.t("help.footer", locale))
        return [Reply("\n\n".join(parts))]

    async def _cmd_start(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        return [
            Reply(
                "\n\n".join(
                    [
                        self.i18n.t("welcome.title", locale, bot_name=self.config.bot_name),
                        self.i18n.t("welcome.body", locale),
                        self.i18n.t("welcome.steps", locale, prefix=self._prefix),
                        self.i18n.t("welcome.hint", locale, prefix=self._prefix),
                    ]
                )
            )
        ]

    async def _cmd_about(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        return [
            Reply(
                self.i18n.t(
                    "about.body", locale, bot_name=self.config.bot_name, version=__version__
                )
            )
        ]

    async def _cmd_status(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        checks = await self.health_report(include_external=True)
        lookup = {check.name: check for check in checks}
        lines = [self.i18n.t("status.title", locale)]
        lines.append(
            f"**{self.i18n.t('status.bot', locale)}:** {self.config.bot_name} v{__version__}"
        )
        lines.append(
            f"**{self.i18n.t('status.uptime', locale)}:** "
            f"{self._format_duration(time.time() - self.started_at)}"
        )

        def render(name: str, label_key: str) -> str:
            check = lookup.get(name)
            if check is None:
                return (
                    f"**{self.i18n.t(label_key, locale)}:** {self.i18n.t('status.unknown', locale)}"
                )
            state = self.i18n.t(f"status.{check.status}", locale)
            detail = f" — {check.detail}" if check.detail and check.status not in {"online"} else ""
            return f"**{self.i18n.t(label_key, locale)}:** {state}{detail}"

        lines.append(render("ollama", "status.ai"))
        lines.append(render("github", "status.github"))
        lines.append(render("database", "status.database"))
        adapters = [
            f"{name}: {self.i18n.t('status.online' if ready else 'status.offline', locale)}"
            for name, ready in self.adapter_states().items()
        ]
        lines.append(f"**{self.i18n.t('status.platforms', locale)}:** {', '.join(adapters) or '—'}")
        if message.is_admin:
            lines.append(self.i18n.t("status.refresh_hint", locale, prefix=self._prefix))
        return [Reply("\n".join(lines))]

    async def _cmd_language(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        if not args:
            return [
                Reply(
                    self.i18n.t(
                        "language.current",
                        locale,
                        language=self.i18n.language_name(locale),
                        prefix=self._prefix,
                    )
                )
            ]
        aliases = {
            "english": "en",
            "中文": "zh",
            "汉语": "zh",
            "chinese": "zh",
            "日本語": "ja",
            "japanese": "ja",
            "日语": "ja",
        }
        requested = aliases.get(args.strip().lower(), args.strip().lower())
        chosen = normalize_locale(requested)
        if not chosen:
            return [Reply(self.i18n.t("language.invalid", locale, prefix=self._prefix))]
        await self.db.set_member_locale(message.platform, message.user_id, chosen)
        return [
            Reply(
                self.i18n.t(
                    "language.set",
                    chosen,
                    language=self.i18n.language_name(chosen),
                )
            )
        ]

    async def _cmd_link(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        if not args:
            return [Reply(self.i18n.t("link.usage", locale, prefix=self._prefix))]
        github_user = args.split()[0].strip().lstrip("@")
        if not GITHUB_USERNAME.fullmatch(github_user):
            return [Reply(self.i18n.t("link.failed", locale, github=github_user))]

        current = await self.db.get_link_for_member(message.platform, message.user_id)
        if current:
            if current.github_user.lower() == github_user.lower():
                return [
                    Reply(
                        self.i18n.t(
                            "link.already",
                            locale,
                            github=current.github_user,
                            points=current.points,
                        )
                    )
                ]
            return [
                Reply(
                    self.i18n.t(
                        "link.already_other",
                        locale,
                        current=current.github_user,
                        new=github_user,
                    )
                )
            ]

        if not self.github.repo_name:
            return [Reply(self.i18n.t("error.github_repo_missing", locale, prefix=self._prefix))]
        try:
            await self.github.ensure_repo()
            totals = await self.github.get_totals(github_user)
        except GitHubError as exc:
            if exc.status == 404:
                return [Reply(self.i18n.t("link.failed", locale, github=github_user))]
            logger.warning("GitHub lookup failed for %s: %s", github_user, exc)
            return [Reply(self.i18n.t("error.github_api", locale))]

        try:
            link, _ = await self.db.link_member(
                message.platform,
                message.user_id,
                github_user,
                baseline_points=totals.points,
            )
        except LinkConflict as exc:
            return [
                Reply(
                    self.i18n.t(
                        "link.already_other",
                        locale,
                        current=exc.current_github,
                        new=github_user,
                    )
                )
            ]
        self.metrics.inc("bot_links_total", platform=message.platform)
        return [
            Reply(
                self.i18n.t(
                    "link.success",
                    locale,
                    github=link.github_user,
                    commits=totals.commits,
                    issues=totals.issues,
                    prs=totals.prs,
                    points=link.points,
                )
            )
        ]

    async def _cmd_challenge(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        link = await self.db.get_link_for_member(message.platform, message.user_id)
        if link is None:
            return [Reply(self.i18n.t("challenge.requires_link", locale, prefix=self._prefix))]

        counts = None
        try:
            if self.github.repo_name:
                counts = await self.github.get_totals(link.github_user)
        except GitHubError as exc:
            logger.warning("Challenge totals unavailable for %s: %s", link.github_user, exc)

        if counts:
            activity = self.i18n.t(
                "challenge.activity_summary",
                locale,
                commits=counts.commits,
                issues=counts.issues,
                prs=counts.prs,
            )
        else:
            activity = self.i18n.t("challenge.activity_points", locale, points=link.points)

        try:
            self.metrics.inc("ai_requests_total", task="challenge", result="started")
            challenge = await self.ai.challenge(activity, locale=locale)
            self.metrics.inc("ai_requests_total", task="challenge", result="success")
            await self.db.set_challenge(link.github_user, challenge)
        except AIError as exc:
            self.metrics.inc("ai_requests_total", task="challenge", result=exc.reason)
            challenge = self._fallback_challenge(counts, locale)

        return [Reply(f"{self.i18n.t('challenge.title', locale)}\n\n{challenge}")]

    def _fallback_challenge(self, counts: Any, locale: str) -> str:
        if counts is None or counts.prs == 0:
            key = "challenge.fallback_review"
        elif counts.issues == 0:
            key = "challenge.fallback_issue"
        else:
            key = "challenge.fallback_pair"
        return self.i18n.t(key, locale)

    async def _cmd_leaderboard(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        entries = await self.db.leaderboard(self.config.limits.leaderboard_size)
        if not entries:
            return [Reply(self.i18n.t("leaderboard.empty", locale, prefix=self._prefix))]
        lines = [self.i18n.t("leaderboard.title", locale)]
        for index, entry in enumerate(entries, 1):
            badges = format_badges(entry.badges, self.i18n, locale)
            suffix = self.i18n.t("leaderboard.badges", locale, badges=badges) if badges else ""
            name = entry.display_names[0] if entry.display_names else entry.github_user
            lines.append(
                self.i18n.t(
                    "leaderboard.row",
                    locale,
                    rank=index,
                    name=name,
                    github=entry.github_user,
                    points=entry.points,
                    badges=suffix,
                )
            )
        lines.append(
            self.i18n.t(
                "leaderboard.footer",
                locale,
                commit_points=points_for("commit"),
                issue_points=points_for("issue"),
                pr_points=points_for("pull_request"),
            )
        )
        return [Reply("\n".join(lines))]

    async def _cmd_sentiment(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        if not args:
            return [Reply(self.i18n.t("sentiment.usage", locale, prefix=self._prefix))]
        if len(args) > self.config.limits.max_ai_input_chars:
            return [
                Reply(
                    self.i18n.t(
                        "error.input_too_long",
                        locale,
                        length=len(args),
                        limit=self.config.limits.max_ai_input_chars,
                    )
                )
            ]
        try:
            self.metrics.inc("ai_requests_total", task="sentiment", result="started")
            reflection = await self.ai.reflect_tone(args, locale=locale)
            self.metrics.inc("ai_requests_total", task="sentiment", result="success")
        except AIError as exc:
            self.metrics.inc("ai_requests_total", task="sentiment", result=exc.reason)
            reflection = self._fallback_sentiment(args, locale)
        return [
            Reply(
                "\n\n".join(
                    [
                        self.i18n.t("sentiment.title", locale),
                        reflection,
                        self.i18n.t("sentiment.disclaimer", locale),
                    ]
                )
            )
        ]

    def _fallback_sentiment(self, text: str, locale: str) -> str:
        lowered = text.lower()
        positive = (
            "thank",
            "great",
            "love",
            "nice",
            "awesome",
            "help",
            "谢谢",
            "感谢",
            "太好了",
            "喜欢",
            "ありがとう",
            "素敵",
            "助かり",
            "嬉しい",
        )
        negative = (
            "hate",
            "angry",
            "stupid",
            "useless",
            "terrible",
            "never",
            "糟糕",
            "生气",
            "垃圾",
            "失望",
            "ひどい",
            "怒",
            "最悪",
            "失望",
        )
        score = sum(1 for word in positive if word in lowered) - sum(
            1 for word in negative if word in lowered
        )
        if score > 0:
            tone, tip = "sentiment.positive", "sentiment.tip.positive"
        elif score < 0:
            tone, tip = "sentiment.negative", "sentiment.tip.negative"
        else:
            tone, tip = "sentiment.neutral", "sentiment.tip.neutral"
        return self.i18n.t(
            "sentiment.fallback",
            locale,
            tone=self.i18n.t(tone, locale),
            tip=self.i18n.t(tip, locale),
        )

    async def _cmd_ask(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        if not args:
            return [Reply(self.i18n.t("ask.usage", locale, prefix=self._prefix))]
        if len(args) > self.config.limits.max_ai_input_chars:
            return [
                Reply(
                    self.i18n.t(
                        "error.input_too_long",
                        locale,
                        length=len(args),
                        limit=self.config.limits.max_ai_input_chars,
                    )
                )
            ]
        return await self._answer_with_ai(message, args, locale)

    async def _chat(self, message: IncomingMessage, member: Member, locale: str) -> list[Reply]:
        text = message.text.strip()
        if not text:
            return [Reply(self.i18n.t("welcome.hint", locale, prefix=self._prefix))]
        return await self._answer_with_ai(message, text, locale)

    async def _answer_with_ai(
        self, message: IncomingMessage, text: str, locale: str
    ) -> list[Reply]:
        key = f"{message.platform}:{message.channel_id}:{message.user_id}"
        history = self.memory.history(key)
        try:
            self.metrics.inc("ai_requests_total", task="chat", result="started")
            answer = await self.ai.answer(text, locale=locale, history=history)
            self.metrics.inc("ai_requests_total", task="chat", result="success")
        except AIError as exc:
            self.metrics.inc("ai_requests_total", task="chat", result=exc.reason)
            if exc.reason == "disabled":
                return [Reply(self.i18n.t("error.ai_disabled", locale))]
            if exc.reason == "timeout":
                return [Reply(self.i18n.t("error.ai_timeout", locale))]
            if exc.reason == "model_missing":
                return [Reply(self.i18n.t("ask.offline", locale, prefix=self._prefix))]
            return [Reply(self.i18n.t("error.ai_unavailable", locale))]
        self.memory.add(key, "user", text)
        self.memory.add(key, "assistant", answer)
        return [Reply(answer)]

    async def _cmd_privacy(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        action = args.strip().lower()
        if not action:
            profile = await self.db.get_profile(message.platform, message.user_id)
            link = profile.link if profile else None
            lines = [
                self.i18n.t("privacy.title", locale),
                self.i18n.t("privacy.body", locale),
            ]
            if link:
                lines.append(
                    self.i18n.t(
                        "privacy.stored",
                        locale,
                        github=link.github_user,
                        points=link.points,
                        language=self.i18n.language_name(member.locale or locale),
                    )
                )
            else:
                lines.append(self.i18n.t("privacy.not_linked", locale))
            lines.append(self.i18n.t("privacy.optout", locale, prefix=self._prefix))
            lines.append(self.i18n.t("privacy.help", locale, prefix=self._prefix))
            return [Reply("\n\n".join(lines))]

        if action in {"optout", "opt-out", "退出"}:
            await self.db.set_opted_out(message.platform, message.user_id, True)
            return [Reply(self.i18n.t("privacy.opted_out", locale, prefix=self._prefix))]
        if action in {"optin", "opt-in", "加入"}:
            await self.db.set_opted_out(message.platform, message.user_id, False)
            return [Reply(self.i18n.t("privacy.optin", locale))]
        if action in {"delete", "删除", "delete confirm"}:
            if not message.is_dm:
                return [Reply(self.i18n.t("privacy.dm_only_delete", locale))]
            if action != "delete confirm":
                return [Reply(self.i18n.t("privacy.delete_confirm", locale, prefix=self._prefix))]
            self.memory.clear(f"{message.platform}:{message.channel_id}:{message.user_id}")
            await self.db.delete_member(message.platform, message.user_id)
            return [Reply(self.i18n.t("privacy.deleted", locale))]
        return [Reply(self.i18n.t("privacy.help", locale, prefix=self._prefix))]

    async def _cmd_set_repo(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        if not message.is_admin:
            return [Reply(self.i18n.t("error.admin_only", locale, prefix=self._prefix))]
        if not args:
            return [Reply(self.i18n.t("repo.usage", locale, prefix=self._prefix))]
        repo_name = args.split()[0]
        if not REPO_PATTERN.fullmatch(repo_name):
            return [Reply(self.i18n.t("error.repo_invalid", locale, prefix=self._prefix))]
        try:
            info = await self.github.select_repo(repo_name)
        except GitHubError as exc:
            if exc.status == 404:
                return [Reply(self.i18n.t("error.repo_not_found", locale, repo=repo_name))]
            return [Reply(self.i18n.t("error.github_api", locale))]
        await self.db.set_setting("github_repo", info.full_name)
        self.metrics.inc("bot_repo_changes_total")
        return [Reply(self.i18n.t("repo.set", locale, repo=info.full_name))]

    async def _cmd_refresh(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        if not message.is_admin:
            return [Reply(self.i18n.t("error.admin_only", locale, prefix=self._prefix))]
        if not self.github.repo_name:
            return [Reply(self.i18n.t("error.github_repo_missing", locale, prefix=self._prefix))]
        if self._poll_lock.locked():
            return [Reply(self.i18n.t("admin.refresh.running", locale))]
        result = await self.poll_once()
        return [
            Reply(
                self.i18n.t(
                    "admin.refresh.done",
                    locale,
                    updated=result.get("updated", 0),
                    points=result.get("points", 0),
                )
            )
        ]

    async def _cmd_unlink(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        if not message.is_admin:
            return [Reply(self.i18n.t("error.admin_only", locale, prefix=self._prefix))]
        if not args:
            return [Reply(self.i18n.t("admin.unlink.usage", locale, prefix=self._prefix))]
        target = args.split()[0]
        platform, _, user_id = target.partition(":")
        if not user_id:
            platform, user_id = message.platform, target
        github_user = await self.db.unlink_member(platform, user_id)
        if not github_user:
            return [Reply(self.i18n.t("error.not_linked", locale, prefix=self._prefix))]
        return [
            Reply(
                self.i18n.t(
                    "admin.unlink.done",
                    locale,
                    member=f"{platform}:{user_id}",
                    github=github_user,
                )
            )
        ]

    async def _cmd_shutdown(
        self, message: IncomingMessage, member: Member, args: str, locale: str
    ) -> list[Reply]:
        if not message.is_admin:
            return [Reply(self.i18n.t("error.admin_only", locale, prefix=self._prefix))]
        if not self.config.allow_remote_shutdown:
            return [Reply(self.i18n.t("admin.shutdown.disabled", locale))]
        if args.strip().lower() != "confirm":
            return [Reply(self.i18n.t("admin.shutdown.confirm", locale, prefix=self._prefix))]
        logger.info("Remote shutdown requested by %s/%s", message.platform, message.user_id)
        self.shutdown_event.set()
        return [Reply(self.i18n.t("admin.shutdown.done", locale))]

    # -------------------------------------------------------------------- polling

    async def poll_once(self) -> dict[str, int]:
        if not self.github.repo_name:
            return {"updated": 0, "points": 0, "awarded": 0}
        async with self._poll_lock:
            run_started = datetime.now(UTC)
            links = await self.db.list_links_for_polling()
            updated = 0
            awarded = 0
            points = 0
            for link in links:
                since = link.last_activity_check or (run_started - timedelta(days=30))
                try:
                    items = await self.github.recent_activity(link.github_user, since)
                except GitHubError as exc:
                    logger.warning("Poll failed for %s: %s", link.github_user, exc)
                    continue
                for item in items:
                    if await self.db.award_for_user(link.github_user, item, "poll"):
                        awarded += 1
                        points += item.points
                await self.db.touch_activity_check(link.github_user, run_started)
                updated += 1
            self.last_poll_at = run_started
            self.last_poll_result = {
                "updated": updated,
                "awarded": awarded,
                "points": points,
            }
            self.metrics.inc("bot_poll_runs_total")
            self.metrics.inc("bot_activity_awarded_total", awarded)
            logger.info(
                "Poll complete: %s contributors, %s new activities, %s points",
                updated,
                awarded,
                points,
            )
            return self.last_poll_result

    async def _poll_loop(self) -> None:
        if await self._sleep_or_shutdown(10):
            return
        while not self._closing:
            if self.github.repo_name:
                try:
                    await self.poll_once()
                except Exception:
                    logger.exception("Background GitHub poll failed")
                    self.metrics.inc("bot_errors_total", where="poll")
            jitter = random.uniform(0, min(30, self.config.github.poll_interval_seconds * 0.1))
            if await self._sleep_or_shutdown(self.config.github.poll_interval_seconds + jitter):
                return

    async def _maintenance_loop(self) -> None:
        while not self._closing:
            if await self._sleep_or_shutdown(86_400):
                return
            try:
                removed = await self.db.prune_events(self.config.limits.retention_days)
                if removed:
                    logger.info("Pruned %s old activity events", removed)
            except Exception:
                logger.exception("Maintenance task failed")

    async def _sleep_or_shutdown(self, seconds: float) -> bool:
        """Wait, returning True when the process should stop.

        Returning a value (rather than looping on an already-set event) is
        important: a set event otherwise makes ``wait_for`` return immediately
        and starves the event loop during shutdown.
        """

        if self.shutdown_event.is_set():
            return True
        try:
            await asyncio.wait_for(self.shutdown_event.wait(), timeout=seconds)
        except TimeoutError:
            return False
        return True

    # ------------------------------------------------------------------- webhooks

    async def handle_github_webhook(self, event: str, payload: dict[str, Any]) -> dict[str, int]:
        repository = payload.get("repository") or {}
        full_name = repository.get("full_name", "")
        if not full_name or not self.github.repo_name:
            return {"handled": 0, "points": 0}
        if full_name.lower() != self.github.repo_name.lower():
            logger.info("Ignoring GitHub webhook for %s", full_name)
            return {"handled": 0, "points": 0}
        if event == "ping":
            return {"handled": 0, "points": 0}

        handled = 0
        points = 0

        async def award(github_user: str, item: ActivityItem) -> None:
            nonlocal handled, points
            if not github_user:
                return
            if await self.db.award_for_user(github_user, item, "webhook"):
                handled += 1
                points += item.points

        if event == "push":
            for commit in (payload.get("commits") or [])[:200]:
                # GitHub leaves author.username null when an email is not linked.
                # Crediting the pusher in that case would give points to the
                # wrong person, so skip the commit instead.
                author = (commit.get("author") or {}).get("username")
                if not author:
                    continue
                await award(
                    author,
                    ActivityItem(
                        key=f"commit:{full_name}:{commit.get('id', '')}",
                        kind="commit",
                        points=points_for("commit"),
                        title=(commit.get("message") or "").splitlines()[0][:200],
                        url=commit.get("url", ""),
                        created_at=_parse_github_time(commit.get("timestamp")),
                    ),
                )
        elif event == "issues" and payload.get("action") == "opened":
            issue = payload.get("issue") or {}
            await award(
                (issue.get("user") or {}).get("login", ""),
                ActivityItem(
                    key=f"issue:{full_name}:{issue.get('number', '')}",
                    kind="issue",
                    points=points_for("issue"),
                    title=(issue.get("title") or "")[:200],
                    url=issue.get("html_url", ""),
                    created_at=_parse_github_time(issue.get("created_at")),
                ),
            )
        elif event == "pull_request" and payload.get("action") == "opened":
            pull = payload.get("pull_request") or {}
            await award(
                (pull.get("user") or {}).get("login", ""),
                ActivityItem(
                    key=f"pr:{full_name}:{pull.get('number', '')}",
                    kind="pull_request",
                    points=points_for("pull_request"),
                    title=(pull.get("title") or "")[:200],
                    url=pull.get("html_url", ""),
                    created_at=_parse_github_time(pull.get("created_at")),
                ),
            )

        self.metrics.inc("github_webhook_events_total", event=event)
        self.metrics.inc("bot_activity_awarded_total", handled)
        return {"handled": handled, "points": points}

    # --------------------------------------------------------------------- utils

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = int(seconds)
        days, remainder = divmod(total, 86_400)
        hours, remainder = divmod(remainder, 3_600)
        minutes, secs = divmod(remainder, 60)
        if days:
            return f"{days}d {hours}h {minutes}m"
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {secs}s"
        return f"{secs}s"

    def describe_locale(self, locale: str) -> str:
        return LOCALE_LABELS.get(locale, locale)


def _parse_github_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


__all__ = ["CommunityBot", "RateLimiter", "SUPPORTED_LOCALES"]
