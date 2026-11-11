from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from github_community_bot.bot import RateLimiter
from github_community_bot.models import ActivityItem
from github_community_bot.services.ai import AIError


async def test_help_about_and_start(bot, message_factory):
    help_reply = (await bot.handle_message(message_factory("!help")))[0].text
    assert "Test Community Bot" in help_reply
    assert "!leaderboard" in help_reply

    about = (await bot.handle_message(message_factory("!about")))[0].text
    assert "2.1.0" in about
    assert "Ollama" in about

    start = (await bot.handle_message(message_factory("!start")))[0].text
    assert "Welcome" in start


async def test_natural_dm_help_and_localized_replies(bot, message_factory):
    english = (await bot.handle_message(message_factory("help", locale_hint=None)))[0].text
    assert "help" in english.lower()

    chinese = (await bot.handle_message(message_factory("帮助", user_id="u2", locale_hint=None)))[
        0
    ].text
    assert "帮助" in chinese

    japanese = (
        await bot.handle_message(message_factory("ヘルプ", user_id="u3", locale_hint=None))
    )[0].text
    assert "ヘルプ" in japanese


async def test_link_awards_baseline_and_leaderboard(bot, message_factory):
    reply = (await bot.handle_message(message_factory("!link alice")))[0].text
    assert "100 points" in reply
    assert "3 commits" in reply

    leaderboard = (await bot.handle_message(message_factory("!leaderboard")))[0].text
    assert "@alice" in leaderboard
    assert "100 pts" in leaderboard
    assert "Bronze" in leaderboard


async def test_link_requires_repository(bot, fake_github, message_factory, monkeypatch):
    monkeypatch.setattr(fake_github, "repo_name", None)
    reply = (await bot.handle_message(message_factory("!link alice")))[0].text
    assert "No repository" in reply


async def test_already_linked(bot, message_factory):
    await bot.handle_message(message_factory("!link alice"))
    reply = (await bot.handle_message(message_factory("!link Alice")))[0].text
    assert "already linked" in reply


async def test_ai_question_and_memory(bot, fake_ai, message_factory):
    reply = (await bot.handle_message(message_factory("!ask how do I start?")))[0].text
    assert reply == fake_ai.answer_text
    assert fake_ai.answers == ["how do I start?"]


async def test_challenge_ai_and_fallback(bot, fake_ai, message_factory):
    await bot.handle_message(message_factory("!link alice"))
    reply = (await bot.handle_message(message_factory("!challenge")))[0].text
    assert fake_ai.challenge_text in reply

    fake_ai.failure = AIError("unavailable")
    fallback = (await bot.handle_message(message_factory("!challenge")))[0].text
    assert "pair" in fallback.lower()


async def test_sentiment_fallback_is_kind(bot, fake_ai, message_factory):
    fake_ai.failure = AIError("unavailable")
    reply = (await bot.handle_message(message_factory("!sentiment this is terrible and useless")))[
        0
    ].text
    assert "Tone check" in reply
    assert "tense" in reply
    assert "not a judgment" in reply


async def test_language_switch_persists(bot, message_factory):
    reply = (await bot.handle_message(message_factory("!language ja")))[0].text
    assert "日本語" in reply
    help_reply = (await bot.handle_message(message_factory("!help")))[0].text
    assert "ヘルプ" in help_reply


async def test_privacy_opt_out_and_in(bot, message_factory):
    await bot.handle_message(message_factory("!privacy optout"))
    blocked = (await bot.handle_message(message_factory("!leaderboard")))[0].text
    assert "opted out" in blocked
    await bot.handle_message(message_factory("!privacy optin"))
    allowed = (await bot.handle_message(message_factory("!help")))[0].text
    assert "help" in allowed.lower()


async def test_privacy_delete_removes_data(bot, db, message_factory):
    await bot.handle_message(message_factory("!link alice"))
    await bot.handle_message(message_factory("!privacy optout"))
    assert await db.get_member("discord", "u1") is not None
    reply = (await bot.handle_message(message_factory("!privacy delete confirm")))[0].text
    assert "deleted" in reply.lower() or "gone" in reply.lower()
    assert await db.get_member("discord", "u1") is None
    assert await db.get_link("Alice") is None


async def test_privacy_delete_requires_dm(bot, message_factory):
    await bot.handle_message(message_factory("!link alice"))
    reply = (await bot.handle_message(message_factory("!privacy delete confirm", is_dm=False)))[
        0
    ].text
    assert "direct message" in reply


async def test_admin_commands(bot, message_factory):
    denied = (await bot.handle_message(message_factory("!set_repo owner/other", is_admin=False)))[
        0
    ].text
    assert "admins" in denied

    changed = (await bot.handle_message(message_factory("!set_repo owner/other", is_admin=True)))[
        0
    ].text
    assert "owner/other" in changed

    shutdown = (await bot.handle_message(message_factory("!shutdown confirm", is_admin=True)))[
        0
    ].text
    assert "disabled" in shutdown
    assert bot.shutdown_event.is_set() is False


async def test_unknown_command(bot, message_factory):
    reply = (await bot.handle_message(message_factory("!wat")))[0].text
    assert "don't know" in reply


async def test_rate_limit(bot, message_factory):
    bot.rate_limiter = RateLimiter(limit=1)
    assert (await bot.handle_message(message_factory("hello")))[0].text
    limited = (await bot.handle_message(message_factory("hello again")))[0].text
    assert "wait" in limited.lower()


async def test_status(bot, message_factory):
    reply = (await bot.handle_message(message_factory("!status", is_admin=True)))[0].text
    assert "Bot status" in reply
    assert "Ollama" in reply
    assert "GitHub" in reply


async def test_github_webhook_awards_once(bot, db, message_factory):
    await bot.handle_message(message_factory("!link alice"))
    payload = {
        "repository": {"full_name": "cxy2696/GitHub-Community-Bot"},
        "action": "opened",
        "issue": {
            "number": 5,
            "title": "Improve docs",
            "html_url": "https://example.test/issues/5",
            "created_at": "2026-11-11T00:00:00Z",
            "user": {"login": "Alice"},
        },
    }
    first = await bot.handle_github_webhook("issues", payload)
    assert first == {"handled": 1, "points": 20}
    second = await bot.handle_github_webhook("issues", payload)
    assert second == {"handled": 0, "points": 0}
    link = await db.get_link("Alice")
    assert link is not None and link.points == 120


async def test_github_webhook_ignores_other_repo(bot):
    result = await bot.handle_github_webhook(
        "issues", {"repository": {"full_name": "someone/else"}}
    )
    assert result == {"handled": 0, "points": 0}


async def test_poll_awards_once(bot, fake_github, db, message_factory):
    await bot.handle_message(message_factory("!link alice"))
    fake_github.recent = [
        ActivityItem(
            key="commit:cxy2696/GitHub-Community-Bot:abc",
            kind="commit",
            points=10,
            title="Docs",
            created_at=datetime.now(UTC),
        )
    ]
    first = await bot.poll_once()
    assert first["awarded"] == 1
    second = await bot.poll_once()
    assert second["awarded"] == 0
    link = await db.get_link("Alice")
    assert link is not None and link.points == 110


async def test_shutdown_signal_does_not_spin(bot):
    bot.shutdown_event.set()
    assert await asyncio.wait_for(bot._sleep_or_shutdown(60), timeout=0.5) is True
    await asyncio.wait_for(bot._poll_loop(), timeout=0.5)
