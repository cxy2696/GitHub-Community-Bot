"""Shared adapter contract and message chunking."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from ..models import IncomingMessage, Reply

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import CommunityBot

logger = logging.getLogger(__name__)


def chunk_text(text: str, limit: int) -> list[str]:
    """Split text on paragraph/word boundaries without dropping content."""

    if limit < 1:
        raise ValueError("limit must be positive")
    remaining = text.strip()
    chunks: list[str] = []
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        chunk = remaining[:cut].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks or [""]


class PlatformAdapter(ABC):
    name: str = "unknown"

    def __init__(self) -> None:
        self.bot: CommunityBot | None = None
        self.ready = False

    @abstractmethod
    async def start(self, bot: CommunityBot) -> None:
        """Begin receiving messages. Must not block forever."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop receiving and release resources."""

    @abstractmethod
    async def deliver(self, channel_id: str, reply: Reply, *, thread_id: str | None = None) -> None:
        """Send one reply to a channel."""

    async def dispatch(self, incoming: IncomingMessage, *, thread_id: str | None = None) -> None:
        if self.bot is None:
            return
        replies = await self.bot.handle_message(incoming)
        for reply in replies:
            try:
                await self.deliver(incoming.channel_id, reply, thread_id=thread_id)
            except Exception:
                logger.exception("Failed to deliver a reply on %s", self.name)
                self.bot.metrics.inc("bot_errors_total", where=f"deliver_{self.name}")

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "ready": self.ready}
