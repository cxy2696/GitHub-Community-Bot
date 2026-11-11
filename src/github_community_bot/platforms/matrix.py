"""Matrix adapter using the client-server /sync long-poll API.

End-to-end encrypted rooms are intentionally out of scope: the bot needs the
room key to read messages, and silently failing would be worse than documenting
that Matrix support targets unencrypted community rooms.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import aiohttp

from ..config import MatrixConfig
from ..models import IncomingMessage, Reply
from .base import PlatformAdapter, chunk_text

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import CommunityBot

logger = logging.getLogger(__name__)


class MatrixAdapter(PlatformAdapter):
    name = "matrix"

    def __init__(self, config: MatrixConfig) -> None:
        super().__init__()
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._task: asyncio.Task[None] | None = None
        self._closing = False
        self._since: str | None = None
        self._user_id = config.user_id
        self._validated = False

    async def start(self, bot: CommunityBot) -> None:
        self.bot = bot
        self._closing = False
        assert self.config.homeserver is not None
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=45),
            headers={"Authorization": f"Bearer {self.config.access_token}"},
        )
        self._task = asyncio.create_task(self._run(), name="matrix-adapter")
        self._task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self.ready = False
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Matrix adapter stopped with an error")

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
                if not self._validated:
                    identity = await self._api("GET", "/_matrix/client/v3/account/whoami")
                    self._user_id = str(identity.get("user_id") or self.config.user_id)
                    self._validated = True
                    logger.info("Matrix connected as %s", self._user_id)
                if self._since is None:
                    initial = await self._sync(timeout=0, since=None)
                    self._since = str(initial.get("next_batch") or "") or None
                self.ready = True
                response = await self._sync(timeout=30, since=self._since)
                self._since = str(response.get("next_batch") or self._since or "") or None
                await self._handle_sync(response)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.ready = False
                logger.warning("Matrix sync problem: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _sync(self, timeout: int, since: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"timeout": timeout}
        if since:
            params["since"] = since
        return await self._api("GET", "/_matrix/client/v3/sync", params=params)

    async def _handle_sync(self, response: dict[str, Any]) -> None:
        rooms = (response.get("rooms") or {}).get("join") or {}
        for room_id, room in rooms.items():
            if self.config.room_ids and room_id not in self.config.room_ids:
                continue
            events = (room.get("timeline") or {}).get("events") or []
            for event in events:
                await self._handle_event(room_id, event)

    async def _handle_event(self, room_id: str, event: dict[str, Any]) -> None:
        if self.bot is None:
            return
        if event.get("type") != "m.room.message":
            return
        sender = str(event.get("sender", ""))
        if sender == self._user_id:
            return
        content = event.get("content") or {}
        if content.get("msgtype") != "m.text":
            return
        body = content.get("body")
        if not isinstance(body, str) or not body.strip():
            return
        mentions = (content.get("m.mentions") or {}).get("user_ids") or []
        mentioned = bool(self._user_id and self._user_id in mentions) or bool(
            self._user_id and self._user_id in body
        )
        if self._user_id:
            body = body.replace(self._user_id, "").strip()
        if not mentioned and not any(
            body.startswith(prefix) for prefix in self.bot.config.command_prefixes
        ):
            return
        localpart = sender.split(":", 1)[0].lstrip("@")
        incoming = IncomingMessage(
            platform=self.name,
            channel_id=room_id,
            user_id=sender,
            user_name=localpart or sender,
            text=body,
            message_id=str(event.get("event_id", "")),
            is_dm=False,
            mentions_bot=mentioned,
            is_admin=sender in self.config.admin_ids,
        )
        await self.dispatch(incoming)

    async def _api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._session is None or self.config.homeserver is None:
            raise RuntimeError("Matrix session is not ready")
        url = f"{self.config.homeserver}{path}"
        async with self._session.request(method, url, params=params, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(f"Matrix {path} failed: {response.status} {data}")
            return data

    async def deliver(self, channel_id: str, reply: Reply, *, thread_id: str | None = None) -> None:
        txn_id = uuid.uuid4().hex
        path = f"/_matrix/client/v3/rooms/{quote(channel_id, safe='')}/send/m.room.message/{txn_id}"
        for chunk in chunk_text(reply.text, 4000):
            await self._api(
                "PUT",
                path,
                payload={"msgtype": "m.text", "body": chunk},
            )
