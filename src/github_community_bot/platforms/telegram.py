"""Telegram adapter using the long-polling Bot API."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import aiohttp

from ..config import TelegramConfig
from ..models import IncomingMessage, Reply
from .base import PlatformAdapter, chunk_text

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import CommunityBot

logger = logging.getLogger(__name__)

COMMANDS = {
    "en": [
        ("help", "Show what I can do"),
        ("start", "Quick tour"),
        ("link", "Connect your GitHub account"),
        ("challenge", "Get a personal next step"),
        ("leaderboard", "Community leaderboard"),
        ("ask", "Ask the local AI"),
        ("language", "English / 中文 / 日本語"),
        ("privacy", "Your data choices"),
        ("status", "Bot health"),
    ],
    "zh": [
        ("help", "查看帮助"),
        ("start", "快速上手"),
        ("link", "绑定 GitHub 账号"),
        ("challenge", "领取专属小目标"),
        ("leaderboard", "社区排行榜"),
        ("ask", "询问本地 AI"),
        ("language", "English / 中文 / 日本語"),
        ("privacy", "隐私与数据设置"),
        ("status", "机器人状态"),
    ],
    "ja": [
        ("help", "ヘルプを見る"),
        ("start", "かんたんガイド"),
        ("link", "GitHub アカウントを連携"),
        ("challenge", "次の一歩を受け取る"),
        ("leaderboard", "コミュニティランキング"),
        ("ask", "ローカル AI に質問"),
        ("language", "English / 中文 / 日本語"),
        ("privacy", "データ設定"),
        ("status", "Bot の状態"),
    ],
}


class TelegramAdapter(PlatformAdapter):
    name = "telegram"

    def __init__(self, config: TelegramConfig) -> None:
        super().__init__()
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._task: asyncio.Task[None] | None = None
        self._closing = False
        self._username: str | None = None
        self._offset = 0

    async def start(self, bot: CommunityBot) -> None:
        self.bot = bot
        self._closing = False
        stored = await bot.db.get_setting("telegram_offset")
        self._offset = int(stored) if stored and stored.isdigit() else 0
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=50))
        self._task = asyncio.create_task(self._run(), name="telegram-adapter")
        self._task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self.ready = False
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Telegram adapter stopped with an error")

    async def stop(self) -> None:
        self._closing = True
        self.ready = False
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
        self._task = None

    async def _run(self) -> None:
        backoff = 1.0
        while not self._closing:
            try:
                if self._username is None:
                    me = await self._api("getMe", {})
                    self._username = str((me.get("result") or {}).get("username") or "") or None
                    logger.info("Telegram connected as @%s", self._username)
                    await self._register_commands()
                    if self._offset == 0:
                        await self._prime_offset()
                self.ready = True
                updates = await self._api(
                    "getUpdates",
                    {
                        "offset": self._offset,
                        "timeout": 30,
                        "allowed_updates": ["message"],
                    },
                )
                for update in updates.get("result") or []:
                    self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                    if self.bot is not None:
                        await self.bot.db.set_setting("telegram_offset", str(self._offset))
                    await self._handle_update(update)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.ready = False
                logger.warning("Telegram polling problem: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _prime_offset(self) -> None:
        data = await self._api("getUpdates", {"offset": -1, "limit": 1, "timeout": 0})
        updates = data.get("result") or []
        if updates:
            self._offset = int(updates[-1].get("update_id", 0)) + 1
            if self.bot is not None:
                await self.bot.db.set_setting("telegram_offset", str(self._offset))

    async def _register_commands(self) -> None:
        for language, commands in COMMANDS.items():
            try:
                await self._api(
                    "setMyCommands",
                    {
                        "commands": [
                            {"command": name, "description": description}
                            for name, description in commands
                        ],
                        "language_code": language,
                    },
                )
            except Exception as exc:
                logger.debug("Could not set Telegram commands for %s: %s", language, exc)

    async def _handle_update(self, update: dict[str, Any]) -> None:
        if self.bot is None:
            return
        message = update.get("message") or {}
        if not message or message.get("from", {}).get("is_bot"):
            return
        chat = message.get("chat") or {}
        if self.config.chat_ids and str(chat.get("id")) not in self.config.chat_ids:
            return
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        user = message.get("from") or {}
        user_id = str(user.get("id", ""))
        is_dm = chat.get("type") == "private"
        mentioned = bool(self._username and f"@{self._username}".lower() in text.lower())
        if self._username:
            text = text.replace(f"@{self._username}", "").strip()
        if (
            not is_dm
            and not mentioned
            and not any(text.startswith(prefix) for prefix in self.bot.config.command_prefixes)
        ):
            return
        name_parts = [user.get("first_name"), user.get("last_name")]
        display = " ".join(part for part in name_parts if part) or user.get("username") or user_id
        incoming = IncomingMessage(
            platform=self.name,
            channel_id=str(chat.get("id", "")),
            user_id=user_id,
            user_name=str(display),
            text=text,
            message_id=str(message.get("message_id", "")),
            is_dm=is_dm,
            mentions_bot=mentioned or is_dm,
            is_admin=user_id in self.config.admin_ids,
            locale_hint=str(user.get("language_code") or "") or None,
            reply_to=str(message.get("message_thread_id") or "") or None,
        )
        await self.dispatch(incoming)

    async def _api(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("Telegram session is not ready")
        url = f"{self.config.api_base}/bot{self.config.token}/{method}"
        async with self._session.post(url, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status != 200 or not data.get("ok"):
                description = data.get("description") or f"HTTP {response.status}"
                raise RuntimeError(f"Telegram {method} failed: {description}")
            return data

    async def deliver(self, channel_id: str, reply: Reply, *, thread_id: str | None = None) -> None:
        for chunk in chunk_text(reply.text, 4000):
            await self._api(
                "sendMessage",
                {
                    "chat_id": channel_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
            )
