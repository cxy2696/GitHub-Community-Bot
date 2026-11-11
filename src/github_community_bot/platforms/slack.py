"""Slack adapter using Socket Mode (no public request URL required)."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING, Any

import aiohttp

from ..commands import strip_bot_mention
from ..config import SlackConfig
from ..models import IncomingMessage, Reply
from .base import PlatformAdapter, chunk_text

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import CommunityBot

logger = logging.getLogger(__name__)
SLACK_API = "https://slack.com/api"


class SlackAdapter(PlatformAdapter):
    name = "slack"

    def __init__(self, config: SlackConfig) -> None:
        super().__init__()
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._task: asyncio.Task[None] | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._closing = False
        self._display_names: dict[str, str] = {}
        self._seen: deque[str] = deque(maxlen=500)
        self._event_tasks: set[asyncio.Task[Any]] = set()
        self._bot_user_id: str | None = None

    async def start(self, bot: CommunityBot) -> None:
        self.bot = bot
        self._closing = False
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=40),
            headers={"Authorization": f"Bearer {self.config.bot_token}"},
        )
        self._task = asyncio.create_task(self._run(), name="slack-adapter")
        self._task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self.ready = False
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Slack adapter stopped with an error")

    async def stop(self) -> None:
        self._closing = True
        self.ready = False
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        for task in list(self._event_tasks):
            task.cancel()
        if self._event_tasks:
            await asyncio.gather(*self._event_tasks, return_exceptions=True)
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
        self._task = None

    async def _run(self) -> None:
        assert self._session is not None
        try:
            identity = await self._api("auth.test", {})
            self._bot_user_id = str(identity.get("user_id") or "") or None
            logger.info("Slack authenticated as %s", identity.get("user") or self._bot_user_id)
        except Exception as exc:
            logger.warning("Slack auth.test failed: %s", exc)

        backoff = 1.0
        while not self._closing:
            try:
                url = await self._open_connection()
                self._ws = await self._session.ws_connect(url, heartbeat=30)
                logger.info("Slack Socket Mode connected")
                async for message in self._ws:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_envelope(message.json())
                    elif message.type in {
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    }:
                        break
                self.ready = False
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.ready = False
                logger.warning("Slack Socket Mode connection problem: %s", exc)
            if self._closing:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)

    async def _open_connection(self) -> str:
        assert self._session is not None
        async with self._session.post(
            f"{SLACK_API}/apps.connections.open",
            headers={"Authorization": f"Bearer {self.config.app_token}"},
        ) as response:
            data = await response.json()
        if not data.get("ok"):
            raise RuntimeError(f"apps.connections.open failed: {data.get('error')}")
        return str(data["url"])

    async def _handle_envelope(self, payload: dict[str, Any]) -> None:
        kind = payload.get("type")
        if kind == "hello":
            self.ready = True
            return
        if kind == "disconnect":
            self.ready = False
            if self._ws is not None:
                await self._ws.close()
            return
        if kind != "events_api":
            return
        envelope_id = payload.get("envelope_id")
        if envelope_id and self._ws is not None and not self._ws.closed:
            await self._ws.send_json({"envelope_id": envelope_id})
        event = (payload.get("payload") or {}).get("event") or {}
        event_id = payload.get("event_id") or event.get("client_msg_id") or ""
        if event_id and event_id in self._seen:
            return
        if event_id:
            self._seen.append(event_id)
        task = asyncio.create_task(self._handle_event(event))
        self._event_tasks.add(task)
        task.add_done_callback(self._event_tasks.discard)

    async def _handle_event(self, event: dict[str, Any]) -> None:
        if self.bot is None:
            return
        if event.get("subtype") or event.get("bot_id"):
            return
        event_type = event.get("type")
        if event_type not in {"message", "app_mention"}:
            return
        channel = str(event.get("channel", ""))
        if self.config.channel_ids and channel not in self.config.channel_ids:
            return
        text = str(event.get("text", ""))
        is_dm = event.get("channel_type") == "im" or (
            channel.startswith("D") and not channel.startswith("C")
        )
        mentioned = event_type == "app_mention" or (
            bool(self._bot_user_id) and f"<@{self._bot_user_id}>" in text
        )
        if event_type == "message" and not is_dm and not mentioned:
            return
        if not text.strip():
            return
        text = _strip_leading_mention(text)
        user_id = str(event.get("user", ""))
        incoming = IncomingMessage(
            platform=self.name,
            channel_id=channel,
            user_id=user_id,
            user_name=await self._display_name(user_id),
            text=text,
            message_id=str(event.get("ts", "")),
            is_dm=is_dm,
            mentions_bot=mentioned or is_dm,
            is_admin=user_id in self.config.admin_ids,
            reply_to=str(event.get("thread_ts") or event.get("ts") or ""),
        )
        thread_id = None if is_dm else str(event.get("thread_ts") or event.get("ts") or "")
        await self.dispatch(incoming, thread_id=thread_id)

    async def _display_name(self, user_id: str) -> str:
        if not user_id:
            return "unknown"
        if user_id in self._display_names:
            return self._display_names[user_id]
        name = user_id
        try:
            data = await self._api("users.info", {"user": user_id})
            user = data.get("user") or {}
            profile = user.get("profile") or {}
            name = (
                profile.get("display_name")
                or profile.get("real_name")
                or user.get("real_name")
                or user.get("name")
                or user_id
            )
        except Exception:
            logger.debug("Could not fetch Slack display name for %s", user_id)
        self._display_names[user_id] = str(name)
        return str(name)

    async def _api(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("Slack session is not ready")
        for attempt in range(2):
            async with self._session.post(f"{SLACK_API}/{method}", json=payload) as response:
                if response.status == 429 and attempt == 0:
                    retry = int(response.headers.get("Retry-After", "1"))
                    await asyncio.sleep(min(retry, 30))
                    continue
                data = await response.json()
                if not data.get("ok"):
                    raise RuntimeError(f"Slack {method} failed: {data.get('error')}")
                return data
        raise RuntimeError(f"Slack {method} rate limited")

    async def deliver(self, channel_id: str, reply: Reply, *, thread_id: str | None = None) -> None:
        for chunk in chunk_text(reply.text, 3000):
            payload: dict[str, Any] = {"channel": channel_id, "text": chunk}
            if thread_id:
                payload["thread_ts"] = thread_id
            await self._api("chat.postMessage", payload)


def _strip_leading_mention(text: str) -> str:
    value = text.strip()
    stripped, mentioned = strip_bot_mention(value)
    return stripped if mentioned else value
