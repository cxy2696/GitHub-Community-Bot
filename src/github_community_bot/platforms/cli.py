"""A local terminal adapter for demos, development and smoke tests."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from ..models import IncomingMessage, Reply
from .base import PlatformAdapter

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import CommunityBot


class CLIAdapter(PlatformAdapter):
    name = "cli"

    def __init__(self) -> None:
        super().__init__()
        self._task: asyncio.Task[None] | None = None

    async def start(self, bot: CommunityBot) -> None:
        self.bot = bot
        self.ready = True
        print(
            f"\n{bot.config.bot_name} · local demo\n"
            "Type !help to begin, or just say hello. Ctrl+D / Ctrl+C to quit.\n"
        )
        self._task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        self.ready = False
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _read_loop(self) -> None:
        assert self.bot is not None
        while not self.bot.shutdown_event.is_set():
            try:
                line = await asyncio.to_thread(input, "you> ")
            except (EOFError, KeyboardInterrupt):
                print()
                self.bot.shutdown_event.set()
                return
            if not line.strip():
                continue
            incoming = IncomingMessage(
                platform=self.name,
                channel_id="local",
                user_id="local",
                user_name="Local user",
                text=line,
                message_id="",
                is_dm=True,
                is_admin=True,
                locale_hint=self.bot.config.default_locale,
            )
            await self.dispatch(incoming)
            if self.bot.shutdown_event.is_set():
                return

    async def deliver(self, channel_id: str, reply: Reply, *, thread_id: str | None = None) -> None:
        print(f"bot> {reply.text}\n", flush=True)
        sys.stdout.flush()
