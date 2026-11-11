"""HTTP surface: health, readiness, metrics, generic bridge and GitHub webhook."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING

from aiohttp import web

from .. import __version__
from ..config import SUPPORTED_LOCALES, HttpConfig
from ..i18n import normalize_locale
from ..models import IncomingMessage, Reply
from .base import PlatformAdapter

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import CommunityBot

logger = logging.getLogger(__name__)

BOT_KEY: web.AppKey = web.AppKey("bot", object)
REQUEST_ID_KEY: web.RequestKey = web.RequestKey("request_id", str)


def _signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _valid_signature(secret: str, body: bytes, provided: str | None) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(_signature(secret, body), provided.strip())


class HTTPServerAdapter(PlatformAdapter):
    name = "http"

    def __init__(self, config: HttpConfig) -> None:
        super().__init__()
        self.config = config
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self, bot: CommunityBot) -> None:
        self.bot = bot
        app = web.Application(
            client_max_size=self.config.max_body_bytes, middlewares=[self._middleware]
        )
        app[BOT_KEY] = bot
        app.router.add_get("/", self._index)
        app.router.add_get("/healthz", self._healthz)
        app.router.add_get("/readyz", self._readyz)
        app.router.add_get("/metrics", self._metrics)
        app.router.add_get("/version", self._version)
        app.router.add_post("/api/v1/messages", self._bridge_message)
        app.router.add_post("/api/v1/github/webhook", self._github_webhook)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.config.host, self.config.port)
        await self._site.start()
        self.ready = True
        logger.info("HTTP listening on %s:%s", self.config.host, self.config.port)

    async def stop(self) -> None:
        self.ready = False
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None

    async def deliver(self, channel_id: str, reply: Reply, *, thread_id: str | None = None) -> None:
        # Outbound bridge calls are intentionally not invented here: a bridge
        # receives replies synchronously in the POST response. Proactive
        # delivery can be added by a deployment-specific adapter.
        return None

    @web.middleware
    async def _middleware(self, request: web.Request, handler):
        bot: CommunityBot = request.app[BOT_KEY]
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request[REQUEST_ID_KEY] = request_id
        started = time.perf_counter()
        try:
            response = await handler(request)
        except web.HTTPException:
            raise
        except Exception:
            logger.exception(
                "HTTP handler failed (%s %s, request %s)", request.method, request.path, request_id
            )
            bot.metrics.inc("http_errors_total", path=request.path)
            response = web.json_response(
                {"ok": False, "error": "internal_error", "request_id": request_id},
                status=500,
            )
        response.headers["X-Request-ID"] = request_id
        route = getattr(request.match_info, "route", None)
        path = getattr(getattr(route, "resource", None), "canonical", None) or "unknown"
        bot.metrics.inc(
            "http_requests_total",
            method=request.method,
            path=path,
            status=str(response.status),
        )
        bot.metrics.inc("http_request_duration_seconds_sum", time.perf_counter() - started)
        return response

    async def _index(self, request: web.Request) -> web.Response:
        bot: CommunityBot = request.app[BOT_KEY]
        return web.json_response(
            {
                "name": bot.config.bot_name,
                "version": __version__,
                "docs": "https://github.com/cxy2696/GitHub-Discord-Bot",
                "endpoints": [
                    "/healthz",
                    "/readyz",
                    "/metrics",
                    "/api/v1/messages",
                    "/api/v1/github/webhook",
                ],
                "model": bot.config.ollama.model,
                "locales": list(SUPPORTED_LOCALES),
            }
        )

    async def _healthz(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "version": __version__})

    async def _readyz(self, request: web.Request) -> web.Response:
        bot: CommunityBot = request.app[BOT_KEY]
        ready, payload = await bot.readiness()
        payload["checks"] = [
            check.as_dict() for check in await bot.health_report(include_external=False)
        ]
        return web.json_response(payload, status=200 if ready else 503)

    async def _metrics(self, request: web.Request) -> web.Response:
        bot: CommunityBot = request.app[BOT_KEY]
        return web.Response(
            text=bot.metrics.render(),
            content_type="text/plain",
            charset="utf-8",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    async def _version(self, request: web.Request) -> web.Response:
        return web.json_response({"version": __version__})

    async def _bridge_message(self, request: web.Request) -> web.Response:
        bot: CommunityBot = request.app[BOT_KEY]
        secret = self.config.bridge_secret
        if not secret:
            return web.json_response(
                {
                    "ok": False,
                    "error": "bridge_disabled",
                    "detail": "BRIDGE_SHARED_SECRET is not set",
                },
                status=503,
            )
        raw = await request.read()
        timestamp = request.headers.get("X-Bridge-Timestamp")
        signed = raw
        if timestamp:
            try:
                ts = int(timestamp)
            except ValueError:
                return web.json_response({"ok": False, "error": "invalid_timestamp"}, status=401)
            if abs(time.time() - ts) > 300:
                return web.json_response({"ok": False, "error": "stale_timestamp"}, status=401)
            signed = f"{timestamp}.".encode() + raw
        if not _valid_signature(secret, signed, request.headers.get("X-Bridge-Signature")):
            return web.json_response({"ok": False, "error": "invalid_signature"}, status=401)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"ok": False, "error": "invalid_payload"}, status=400)

        text = payload.get("text")
        user_id = payload.get("user_id")
        if not isinstance(text, str) or not text.strip():
            return web.json_response({"ok": False, "error": "text_required"}, status=400)
        if not isinstance(user_id, str) or not user_id.strip():
            return web.json_response({"ok": False, "error": "user_id_required"}, status=400)

        user_name = str(payload.get("user_name") or user_id)
        channel_id = str(payload.get("channel_id") or "bridge")
        locale_hint = normalize_locale(str(payload.get("locale") or ""))
        platform = bot.config.bridge.platform_name
        incoming = IncomingMessage(
            platform=platform,
            channel_id=channel_id,
            user_id=user_id,
            user_name=user_name,
            text=text[:8000],
            message_id=str(payload.get("message_id") or ""),
            is_dm=bool(payload.get("is_dm", False)),
            mentions_bot=bool(payload.get("mentions_bot", False)),
            is_admin=user_id in bot.config.bridge.admin_ids,
            locale_hint=locale_hint,
            reply_to=str(payload.get("reply_to") or "") or None,
        )
        replies = await bot.handle_message(incoming)
        return web.json_response(
            {
                "ok": True,
                "request_id": request[REQUEST_ID_KEY],
                "replies": [reply.as_dict() for reply in replies],
            }
        )

    async def _github_webhook(self, request: web.Request) -> web.Response:
        bot: CommunityBot = request.app[BOT_KEY]
        secret = bot.config.github.webhook_secret
        if not secret:
            return web.json_response({"ok": False, "error": "github_webhook_disabled"}, status=503)
        raw = await request.read()
        if not _valid_signature(secret, raw, request.headers.get("X-Hub-Signature-256")):
            return web.json_response({"ok": False, "error": "invalid_signature"}, status=401)
        event = request.headers.get("X-GitHub-Event", "")
        if not event:
            return web.json_response({"ok": False, "error": "event_header_required"}, status=400)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"ok": False, "error": "invalid_payload"}, status=400)
        result = await bot.handle_github_webhook(event, payload)
        logger.info(
            "GitHub webhook %s delivery=%s handled=%s",
            event,
            request.headers.get("X-GitHub-Delivery", "-"),
            result.get("handled", 0),
        )
        return web.json_response({"ok": True, **result}, status=202)


__all__ = ["HTTPServerAdapter", "_valid_signature"]
