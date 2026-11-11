"""Gamification rules kept deliberately small, testable and easy to tune."""

from __future__ import annotations

from collections.abc import Iterable

from .i18n import I18n
from .models import BADGE_THRESHOLDS, POINTS


def points_for(kind: str) -> int:
    try:
        return POINTS[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown contribution kind: {kind!r}") from exc


def earned_badges(points: int) -> tuple[str, ...]:
    return tuple(key for key, threshold in BADGE_THRESHOLDS if points >= threshold)


def merge_badges(existing: Iterable[str], points: int) -> tuple[str, ...]:
    """Keep historical badges and add any newly earned ones."""

    merged = set(existing)
    merged.update(earned_badges(points))
    order = {key: index for index, (key, _) in enumerate(BADGE_THRESHOLDS)}
    return tuple(sorted(merged, key=lambda key: (order.get(key, 99), key)))


def next_badge(points: int) -> tuple[str, int] | None:
    for key, threshold in BADGE_THRESHOLDS:
        if points < threshold:
            return key, threshold
    return None


def format_badges(badges: Iterable[str], i18n: I18n, locale: str) -> str:
    names = [i18n.t(f"badge.{badge}", locale) for badge in badges]
    return ", ".join(names)


def activity_summary(commits: int, issues: int, prs: int) -> str:
    return f"{commits} commits, {issues} issues, {prs} PRs"
