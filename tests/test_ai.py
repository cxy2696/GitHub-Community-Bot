from __future__ import annotations

import pytest

from github_community_bot.config import OllamaConfig
from github_community_bot.services.ai import AIError, ConversationMemory, OllamaClient


class FakeRequest:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []
        self.payloads = []

    async def __call__(self, method, path, payload=None, **kwargs):
        self.calls.append((method, path))
        self.payloads.append(payload)
        response = self.responses.get(path)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_chat_parses_content_and_uses_locale_prompt(monkeypatch):
    client = OllamaClient(OllamaConfig(model="test-model"))
    fake = FakeRequest({"/api/chat": {"message": {"content": "  hello  "}}})
    monkeypatch.setattr(client, "_request", fake)

    answer = await client.chat([{"role": "user", "content": "hi"}], locale="ja")
    assert answer == "hello"
    system = fake.payloads[0]["messages"][0]
    assert system["role"] == "system"
    assert "日本語" in system["content"]


@pytest.mark.asyncio
async def test_empty_response_is_an_error(monkeypatch):
    client = OllamaClient(OllamaConfig(model="test-model"))
    monkeypatch.setattr(
        client, "_request", FakeRequest({"/api/chat": {"message": {"content": " "}}})
    )
    with pytest.raises(AIError, match="Empty response"):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_health_reports_pulled_and_missing_models(monkeypatch):
    client = OllamaClient(OllamaConfig(model="test-model", health_cache_seconds=0))
    fake = FakeRequest({"/api/tags": {"models": [{"name": "test-model"}]}})
    monkeypatch.setattr(client, "_request", fake)
    assert await client.health(force=True) == ("online", "model test-model")

    fake.responses["/api/tags"] = {"models": [{"name": "other"}]}
    status, detail = await client.health(force=True)
    assert status == "degraded"
    assert "ollama pull test-model" in detail

    fake.responses["/api/tags"] = AIError("unavailable", "connection refused")
    status, detail = await client.health(force=True)
    assert status == "offline"
    assert "connection refused" in detail


@pytest.mark.asyncio
async def test_health_disabled():
    client = OllamaClient(OllamaConfig(enabled=False))
    assert await client.health(force=True) == ("disabled", "OLLAMA_ENABLED=false")


def test_memory_is_bounded_and_clearable():
    memory = ConversationMemory(max_messages=2, ttl_seconds=60)
    memory.add("k", "user", "one")
    memory.add("k", "assistant", "two")
    memory.add("k", "user", "three")
    assert [message["content"] for message in memory.history("k")] == ["two", "three"]
    memory.clear("k")
    assert memory.history("k") == []
