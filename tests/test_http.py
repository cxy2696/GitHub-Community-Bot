from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace

import aiohttp
import pytest

from github_community_bot.config import HttpConfig
from github_community_bot.models import IncomingMessage
from github_community_bot.platforms.http_server import HTTPServerAdapter, _valid_signature


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_signature_helper():
    assert _valid_signature("secret", b"body", sign("secret", b"body")) is True
    assert _valid_signature("secret", b"body", "sha256=bad") is False
    assert _valid_signature("secret", b"body", None) is False


@pytest.mark.asyncio
async def test_bridge_disabled_without_secret(bot):
    adapter = HTTPServerAdapter(HttpConfig(enabled=True, host="127.0.0.1", port=0))
    await adapter.start(bot)
    port = adapter._site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    async with (
        aiohttp.ClientSession() as session,
        session.post(f"http://127.0.0.1:{port}/api/v1/messages", json={}) as resp,
    ):
        assert resp.status == 503
    await adapter.stop()


@pytest.mark.asyncio
async def test_bridge_and_github_webhook(bot, db):
    bot.config = replace(
        bot.config,
        github=replace(bot.config.github, webhook_secret="github-secret"),
    )
    adapter = HTTPServerAdapter(
        HttpConfig(
            enabled=True,
            host="127.0.0.1",
            port=0,
            bridge_secret="bridge-secret",
        )
    )
    bot.register_adapter("http", adapter)
    await adapter.start(bot)
    port = adapter._site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    base = f"http://127.0.0.1:{port}"

    async with aiohttp.ClientSession() as session:
        health = await session.get(f"{base}/healthz")
        assert health.status == 200
        assert (await health.json())["status"] == "ok"

        body = json.dumps(
            {
                "text": "!help",
                "user_id": "bridge-user",
                "user_name": "Bridge Tester",
                "is_dm": True,
            }
        ).encode()
        bad = await session.post(
            f"{base}/api/v1/messages",
            data=body,
            headers={"Content-Type": "application/json", "X-Bridge-Signature": "sha256=bad"},
        )
        assert bad.status == 401

        good = await session.post(
            f"{base}/api/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Bridge-Signature": sign("bridge-secret", body),
            },
        )
        assert good.status == 200
        payload = await good.json()
        assert payload["ok"] is True
        assert text_in_replies(payload, "Test Community Bot")

        await bot.handle_message(
            IncomingMessage(
                platform="bridge",
                channel_id="c",
                user_id="bridge-user",
                user_name="Bridge Tester",
                text="!link alice",
                is_dm=True,
            )
        )
        event_body = json.dumps(
            {
                "repository": {"full_name": "cxy2696/GitHub-Community-Bot"},
                "action": "opened",
                "issue": {
                    "number": 9,
                    "title": "Webhook test",
                    "created_at": "2026-11-11T00:00:00Z",
                    "user": {"login": "Alice"},
                },
            }
        ).encode()
        webhook = await session.post(
            f"{base}/api/v1/github/webhook",
            data=event_body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": sign("github-secret", event_body),
            },
        )
        assert webhook.status == 202
        assert (await webhook.json())["handled"] == 1

        metrics = await session.get(f"{base}/metrics")
        assert metrics.status == 200
        assert "http_requests_total" in await metrics.text()

    await adapter.stop()


def text_in_replies(payload, needle: str) -> bool:
    return any(needle in reply["text"] for reply in payload.get("replies", []))
