from __future__ import annotations

from github_community_bot.gamification import (
    earned_badges,
    format_badges,
    merge_badges,
    next_badge,
    points_for,
)


def test_points_for():
    assert points_for("commit") == 10
    assert points_for("issue") == 20
    assert points_for("pull_request") == 30


def test_badge_thresholds():
    assert earned_badges(0) == ()
    assert earned_badges(99) == ()
    assert earned_badges(100) == ("bronze",)
    assert earned_badges(1000) == ("bronze", "silver", "gold")


def test_merge_badges_keeps_history():
    assert merge_badges(("bronze",), 600) == ("bronze", "silver")
    assert merge_badges(("gold",), 10) == ("gold",)


def test_next_badge():
    assert next_badge(0) == ("bronze", 100)
    assert next_badge(600) == ("gold", 1000)
    assert next_badge(1200) is None


def test_format_badges(i18n):
    assert format_badges(("bronze",), i18n, "zh") == "青铜协作者"
