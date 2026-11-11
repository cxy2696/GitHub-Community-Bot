from __future__ import annotations

from datetime import UTC, datetime

import pytest

from github_community_bot.models import ActivityItem
from github_community_bot.storage import Database, LinkConflict


async def test_link_and_shared_score(db: Database) -> None:
    await db.touch_member("discord", "u1", "Tester")
    await db.touch_member("telegram", "u2", "Tester 2")
    link, created = await db.link_member("discord", "u1", "Alice", baseline_points=100)
    assert created is True
    assert link.points == 100
    assert link.badges == ("bronze",)

    shared, created_again = await db.link_member("telegram", "u2", "alice", baseline_points=500)
    assert created_again is False
    assert shared.points == 100  # never double-count history

    profile = await db.get_profile("telegram", "u2")
    assert profile is not None and profile.link is not None
    assert profile.link.github_user.lower() == "alice"


async def test_one_github_account_per_member(db: Database) -> None:
    await db.touch_member("discord", "u1", "Tester")
    await db.link_member("discord", "u1", "Alice", baseline_points=100)
    with pytest.raises(LinkConflict):
        await db.link_member("discord", "u1", "Bob", baseline_points=10)


async def test_activity_award_is_idempotent(db: Database) -> None:
    await db.touch_member("discord", "u1", "Tester")
    await db.link_member("discord", "u1", "Alice", baseline_points=100)
    item = ActivityItem(
        key="commit:repo:abc",
        kind="commit",
        points=10,
        title="Fix docs",
        created_at=datetime.now(UTC),
    )
    assert await db.award_for_user("Alice", item, "test") is True
    assert await db.award_for_user("Alice", item, "webhook") is False
    link = await db.get_link("Alice")
    assert link is not None and link.points == 110
    assert await db.award_for_user("Nobody", item, "test") is False


async def test_leaderboard_and_badges(db: Database) -> None:
    await db.touch_member("discord", "u1", "Tester")
    await db.touch_member("telegram", "u2", "Tester 2")
    await db.touch_member("discord", "u3", "Bob")
    await db.link_member("discord", "u1", "Alice", baseline_points=1000)
    await db.link_member("telegram", "u2", "Alice", baseline_points=0)
    await db.link_member("discord", "u3", "Bob", baseline_points=20)
    entries = await db.leaderboard(10)
    assert entries[0].github_user == "Alice"
    assert entries[0].points == 1000
    assert "gold" in entries[0].badges
    assert set(entries[0].display_names) == {"Tester", "Tester 2"}


async def test_privacy_delete_removes_orphan_link(db: Database) -> None:
    await db.touch_member("discord", "u1", "Tester")
    await db.touch_member("telegram", "u2", "Tester 2")
    await db.link_member("discord", "u1", "Alice", baseline_points=100)
    await db.link_member("telegram", "u2", "Alice", baseline_points=100)
    assert await db.delete_member("discord", "u1") is True
    assert await db.get_link("Alice") is not None
    assert await db.delete_member("telegram", "u2") is True
    assert await db.get_link("Alice") is None
    assert await db.delete_member("discord", "missing") is False


async def test_settings_and_opt_out(db: Database) -> None:
    await db.touch_member("discord", "u1", "Tester", "zh")
    await db.set_member_locale("discord", "u1", "ja")
    await db.set_opted_out("discord", "u1", True)
    member = await db.get_member("discord", "u1")
    assert member is not None
    assert member.locale == "ja" and member.opted_out is True

    await db.set_setting("github_repo", "owner/repo")
    assert await db.get_setting("github_repo") == "owner/repo"
    assert await db.get_setting("missing") is None


async def test_unlink_member(db: Database) -> None:
    await db.touch_member("discord", "u1", "Tester")
    await db.link_member("discord", "u1", "Alice", baseline_points=100)
    assert await db.unlink_member("discord", "u1") == "Alice"
    assert await db.get_link("Alice") is None
    assert await db.unlink_member("discord", "u1") is None
