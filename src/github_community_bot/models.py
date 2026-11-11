"""Typed values shared by every platform adapter and the core engine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    """A platform-neutral inbound message."""

    platform: str
    channel_id: str
    user_id: str
    user_name: str
    text: str
    message_id: str = ""
    is_dm: bool = False
    mentions_bot: bool = False
    is_admin: bool = False
    locale_hint: str | None = None
    reply_to: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def user_key(self) -> str:
        return f"{self.platform}:{self.user_id}"


@dataclass(frozen=True, slots=True)
class Reply:
    """A platform-neutral outbound message."""

    text: str
    ephemeral: bool = False
    kind: str = "message"

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "ephemeral": self.ephemeral, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class Member:
    platform: str
    user_id: str
    display_name: str
    locale: str | None = None
    opted_out: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Link:
    github_user: str
    points: int = 0
    badges: tuple[str, ...] = ()
    current_challenge: str | None = None
    last_activity_check: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MemberProfile:
    member: Member
    link: Link | None = None


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    github_user: str
    points: int
    badges: tuple[str, ...]
    display_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActivityItem:
    """One idempotent unit of contribution."""

    key: str
    kind: str
    points: int
    title: str = ""
    url: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    name: str
    status: str
    detail: str = ""
    latency_ms: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "latency_ms": self.latency_ms,
        }


# Points are intentionally easy to understand and to tune in one place.
POINTS: dict[str, int] = {"commit": 10, "issue": 20, "pull_request": 30}

# Badge thresholds are checked in order; the highest earned badge is displayed.
BADGE_THRESHOLDS: tuple[tuple[str, int], ...] = (
    ("bronze", 100),
    ("silver", 500),
    ("gold", 1000),
)
