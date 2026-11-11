"""SQLite persistence with a tiny async wrapper and versioned migrations.

The schema separates *members* (a person on a chat platform) from *links*
(a GitHub account). Points belong to the GitHub identity, so linking the same
GitHub account from Discord and Slack shares one score instead of duplicating
it. Activity events are recorded by a stable key, which makes polling and
GitHub webhooks idempotent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from .gamification import merge_badges
from .models import ActivityItem, LeaderboardEntry, Link, Member, MemberProfile

logger = logging.getLogger(__name__)
T = TypeVar("T")


class LinkConflict(RuntimeError):
    def __init__(self, current_github: str) -> None:
        super().__init__(current_github)
        self.current_github = current_github


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS members (
            platform TEXT NOT NULL,
            user_id TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            locale TEXT,
            opted_out INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (platform, user_id)
        );

        CREATE TABLE IF NOT EXISTS links (
            github_user TEXT PRIMARY KEY COLLATE NOCASE,
            points INTEGER NOT NULL DEFAULT 0 CHECK (points >= 0),
            badges TEXT NOT NULL DEFAULT '[]',
            current_challenge TEXT,
            last_activity_check TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS member_links (
            platform TEXT NOT NULL,
            user_id TEXT NOT NULL,
            github_user TEXT NOT NULL COLLATE NOCASE,
            created_at TEXT NOT NULL,
            PRIMARY KEY (platform, user_id),
            FOREIGN KEY (platform, user_id) REFERENCES members(platform, user_id)
                ON DELETE CASCADE,
            FOREIGN KEY (github_user) REFERENCES links(github_user) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_member_links_github
            ON member_links(github_user);

        CREATE TABLE IF NOT EXISTS activity_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT NOT NULL UNIQUE,
            github_user TEXT NOT NULL COLLATE NOCASE,
            kind TEXT NOT NULL,
            points INTEGER NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_activity_events_user
            ON activity_events(github_user);
        CREATE INDEX IF NOT EXISTS idx_activity_events_created
            ON activity_events(created_at);

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """,
    ),
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _row_to_member(row: sqlite3.Row) -> Member:
    return Member(
        platform=row["platform"],
        user_id=row["user_id"],
        display_name=row["display_name"],
        locale=row["locale"],
        opted_out=bool(row["opted_out"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _row_to_link(row: sqlite3.Row) -> Link:
    try:
        badges = tuple(json.loads(row["badges"] or "[]"))
    except (TypeError, json.JSONDecodeError):
        badges = ()
    return Link(
        github_user=row["github_user"],
        points=int(row["points"]),
        badges=badges,
        current_challenge=row["current_challenge"],
        last_activity_check=_parse_dt(row["last_activity_check"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        def _open() -> sqlite3.Connection:
            conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            return conn

        self._conn = await asyncio.to_thread(_open)
        await self._migrate()
        logger.info("Database ready at %s", self.path)

    async def close(self) -> None:
        if self._conn is not None:
            async with self._lock:
                conn = self._conn
                self._conn = None
                await asyncio.to_thread(conn.close)

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def _run(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        async with self._lock:
            return await asyncio.to_thread(operation, self.connection)

    async def _migrate(self) -> None:
        def _apply(conn: sqlite3.Connection) -> None:
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
            for version, script in MIGRATIONS:
                if version <= current:
                    continue
                logger.info("Applying database migration %s", version)
                conn.executescript(script)
                conn.execute(f"PRAGMA user_version = {int(version)}")
                conn.commit()

        await self._run(_apply)

    async def ping(self) -> bool:
        try:
            await self._run(lambda conn: conn.execute("SELECT 1").fetchone())
            return True
        except Exception:  # pragma: no cover - defensive
            logger.exception("Database ping failed")
            return False

    # ------------------------------------------------------------------ members

    async def touch_member(
        self,
        platform: str,
        user_id: str,
        display_name: str,
        locale: str | None = None,
    ) -> Member:
        now = _iso(utcnow())

        def _work(conn: sqlite3.Connection) -> Member:
            conn.execute(
                """
                INSERT INTO members(platform, user_id, display_name, locale, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, user_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    locale = COALESCE(members.locale, excluded.locale),
                    updated_at = excluded.updated_at
                """,
                (platform, user_id, display_name, locale, now, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM members WHERE platform = ? AND user_id = ?",
                (platform, user_id),
            ).fetchone()
            assert row is not None
            return _row_to_member(row)

        return await self._run(_work)

    async def get_member(self, platform: str, user_id: str) -> Member | None:
        def _work(conn: sqlite3.Connection) -> Member | None:
            row = conn.execute(
                "SELECT * FROM members WHERE platform = ? AND user_id = ?",
                (platform, user_id),
            ).fetchone()
            return _row_to_member(row) if row else None

        return await self._run(_work)

    async def set_member_locale(self, platform: str, user_id: str, locale: str) -> None:
        def _work(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE members SET locale = ?, updated_at = ? WHERE platform = ? AND user_id = ?",
                (locale, _iso(utcnow()), platform, user_id),
            )
            conn.commit()

        await self._run(_work)

    async def set_opted_out(self, platform: str, user_id: str, opted_out: bool) -> None:
        def _work(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE members SET opted_out = ?, updated_at = ? "
                "WHERE platform = ? AND user_id = ?",
                (int(opted_out), _iso(utcnow()), platform, user_id),
            )
            conn.commit()

        await self._run(_work)

    async def get_profile(self, platform: str, user_id: str) -> MemberProfile | None:
        member = await self.get_member(platform, user_id)
        if member is None:
            return None
        link = await self.get_link_for_member(platform, user_id)
        return MemberProfile(member=member, link=link)

    # -------------------------------------------------------------------- links

    async def get_link(self, github_user: str) -> Link | None:
        def _work(conn: sqlite3.Connection) -> Link | None:
            row = conn.execute(
                "SELECT * FROM links WHERE github_user = ?", (github_user,)
            ).fetchone()
            return _row_to_link(row) if row else None

        return await self._run(_work)

    async def get_link_for_member(self, platform: str, user_id: str) -> Link | None:
        def _work(conn: sqlite3.Connection) -> Link | None:
            row = conn.execute(
                """
                SELECT l.* FROM links l
                JOIN member_links ml ON ml.github_user = l.github_user
                WHERE ml.platform = ? AND ml.user_id = ?
                """,
                (platform, user_id),
            ).fetchone()
            return _row_to_link(row) if row else None

        return await self._run(_work)

    async def link_member(
        self,
        platform: str,
        user_id: str,
        github_user: str,
        baseline_points: int,
        now: datetime | None = None,
    ) -> tuple[Link, bool]:
        """Attach a GitHub account to a member.

        Returns ``(link, created)`` where ``created`` is true when this GitHub
        identity was new to the database. Existing links are never reset, so a
        second platform sees the same shared score.
        """

        timestamp = now or utcnow()
        stamp = _iso(timestamp)

        def _work(conn: sqlite3.Connection) -> tuple[Link, bool]:
            current = conn.execute(
                "SELECT github_user FROM member_links WHERE platform = ? AND user_id = ?",
                (platform, user_id),
            ).fetchone()
            if current and current["github_user"].lower() != github_user.lower():
                raise LinkConflict(str(current["github_user"]))

            existing = conn.execute(
                "SELECT * FROM links WHERE github_user = ?", (github_user,)
            ).fetchone()
            created = existing is None
            if created:
                points = max(0, int(baseline_points))
                badges = merge_badges((), points)
                conn.execute(
                    """
                    INSERT INTO links(github_user, points, badges, last_activity_check,
                                      created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (github_user, points, json.dumps(badges), stamp, stamp, stamp),
                )
            else:
                points = int(existing["points"])
                badges = merge_badges(tuple(json.loads(existing["badges"] or "[]")), points)
                conn.execute(
                    "UPDATE links SET badges = ?, updated_at = ? WHERE github_user = ?",
                    (json.dumps(badges), stamp, github_user),
                )

            conn.execute(
                """
                INSERT INTO member_links(platform, user_id, github_user, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(platform, user_id) DO UPDATE SET
                    github_user = excluded.github_user
                """,
                (platform, user_id, github_user, stamp),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM links WHERE github_user = ?", (github_user,)
            ).fetchone()
            assert row is not None
            return _row_to_link(row), created

        return await self._run(_work)

    async def ensure_minimum_points(self, github_user: str, minimum: int) -> Link | None:
        """Raise a link's score to at least ``minimum`` (used by v1 imports)."""

        def _work(conn: sqlite3.Connection) -> Link | None:
            row = conn.execute(
                "SELECT * FROM links WHERE github_user = ?", (github_user,)
            ).fetchone()
            if row is None:
                return None
            points = max(int(row["points"]), int(minimum))
            badges = merge_badges(tuple(json.loads(row["badges"] or "[]")), points)
            conn.execute(
                "UPDATE links SET points = ?, badges = ?, updated_at = ? WHERE github_user = ?",
                (points, json.dumps(badges), _iso(utcnow()), github_user),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM links WHERE github_user = ?", (github_user,)
            ).fetchone()
            return _row_to_link(updated) if updated else None

        return await self._run(_work)

    async def unlink_member(self, platform: str, user_id: str) -> str | None:
        def _work(conn: sqlite3.Connection) -> str | None:
            row = conn.execute(
                "SELECT github_user FROM member_links WHERE platform = ? AND user_id = ?",
                (platform, user_id),
            ).fetchone()
            if not row:
                return None
            github_user = str(row["github_user"])
            conn.execute(
                "DELETE FROM member_links WHERE platform = ? AND user_id = ?",
                (platform, user_id),
            )
            remaining = conn.execute(
                "SELECT 1 FROM member_links WHERE github_user = ? LIMIT 1", (github_user,)
            ).fetchone()
            if not remaining:
                conn.execute("DELETE FROM activity_events WHERE github_user = ?", (github_user,))
                conn.execute("DELETE FROM links WHERE github_user = ?", (github_user,))
            conn.commit()
            return github_user

        return await self._run(_work)

    async def delete_member(self, platform: str, user_id: str) -> bool:
        def _work(conn: sqlite3.Connection) -> bool:
            row = conn.execute(
                "SELECT 1 FROM members WHERE platform = ? AND user_id = ?",
                (platform, user_id),
            ).fetchone()
            if not row:
                return False
            link = conn.execute(
                "SELECT github_user FROM member_links WHERE platform = ? AND user_id = ?",
                (platform, user_id),
            ).fetchone()
            conn.execute(
                "DELETE FROM members WHERE platform = ? AND user_id = ?",
                (platform, user_id),
            )
            if link:
                github_user = str(link["github_user"])
                remaining = conn.execute(
                    "SELECT 1 FROM member_links WHERE github_user = ? LIMIT 1", (github_user,)
                ).fetchone()
                if not remaining:
                    conn.execute(
                        "DELETE FROM activity_events WHERE github_user = ?", (github_user,)
                    )
                    conn.execute("DELETE FROM links WHERE github_user = ?", (github_user,))
            conn.commit()
            return True

        return await self._run(_work)

    # ------------------------------------------------------------------ activity

    async def award_for_user(
        self,
        github_user: str,
        item: ActivityItem,
        source: str,
        now: datetime | None = None,
    ) -> bool:
        """Award points once for an activity key.

        Returns ``False`` for duplicate deliveries or GitHub users that are not
        linked. The unique ``event_key`` makes polling and webhooks safe to run
        together.
        """

        recorded = _iso(now or utcnow())
        created = _iso(item.created_at) if item.created_at else recorded

        def _work(conn: sqlite3.Connection) -> bool:
            link = conn.execute(
                "SELECT points, badges FROM links WHERE github_user = ?", (github_user,)
            ).fetchone()
            if link is None:
                return False
            return _award(conn, github_user, item, source, recorded, created)

        return await self._run(_work)

    async def touch_activity_check(self, github_user: str, when: datetime | None = None) -> None:
        def _work(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE links SET last_activity_check = ?, updated_at = ? WHERE github_user = ?",
                (_iso(when or utcnow()), _iso(utcnow()), github_user),
            )
            conn.commit()

        await self._run(_work)

    async def set_challenge(self, github_user: str, challenge: str) -> None:
        def _work(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE links SET current_challenge = ?, updated_at = ? WHERE github_user = ?",
                (challenge, _iso(utcnow()), github_user),
            )
            conn.commit()

        await self._run(_work)

    async def list_links_for_polling(self) -> list[Link]:
        def _work(conn: sqlite3.Connection) -> list[Link]:
            rows = conn.execute(
                "SELECT * FROM links ORDER BY last_activity_check IS NULL, last_activity_check"
            ).fetchall()
            return [_row_to_link(row) for row in rows]

        return await self._run(_work)

    # --------------------------------------------------------------- leaderboard

    async def leaderboard(self, limit: int = 10) -> list[LeaderboardEntry]:
        def _work(conn: sqlite3.Connection) -> list[LeaderboardEntry]:
            rows = conn.execute(
                """
                SELECT l.github_user, l.points, l.badges, m.display_name
                FROM links l
                LEFT JOIN member_links ml ON ml.github_user = l.github_user
                LEFT JOIN members m
                    ON m.platform = ml.platform AND m.user_id = ml.user_id
                WHERE l.github_user IN (
                    SELECT github_user FROM links
                    ORDER BY points DESC, github_user ASC LIMIT ?
                )
                ORDER BY l.points DESC, l.github_user ASC
                """,
                (limit,),
            ).fetchall()
            grouped: dict[str, dict[str, Any]] = {}
            for row in rows:
                entry = grouped.setdefault(
                    row["github_user"],
                    {
                        "points": int(row["points"]),
                        "badges": tuple(json.loads(row["badges"] or "[]")),
                        "names": [],
                    },
                )
                if row["display_name"] and row["display_name"] not in entry["names"]:
                    entry["names"].append(row["display_name"])
            return [
                LeaderboardEntry(
                    github_user=github_user,
                    points=entry["points"],
                    badges=entry["badges"],
                    display_names=tuple(entry["names"]),
                )
                for github_user, entry in grouped.items()
            ]

        return await self._run(_work)

    # ------------------------------------------------------------------ settings

    async def set_setting(self, key: str, value: str) -> None:
        def _work(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, _iso(utcnow())),
            )
            conn.commit()

        await self._run(_work)

    async def get_setting(self, key: str) -> str | None:
        def _work(conn: sqlite3.Connection) -> str | None:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else None

        return await self._run(_work)

    # ------------------------------------------------------------------ upkeep

    async def prune_events(self, retention_days: int) -> int:
        cutoff = _iso(utcnow() - timedelta(days=retention_days))

        def _work(conn: sqlite3.Connection) -> int:
            cursor = conn.execute("DELETE FROM activity_events WHERE recorded_at < ?", (cutoff,))
            conn.commit()
            return cursor.rowcount

        return await self._run(_work)

    async def stats(self) -> dict[str, int]:
        def _work(conn: sqlite3.Connection) -> dict[str, int]:
            def count(table: str) -> int:
                return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

            return {
                "members": count("members"),
                "links": count("links"),
                "events": count("activity_events"),
            }

        return await self._run(_work)


def _award(
    conn: sqlite3.Connection,
    github_user: str,
    item: ActivityItem,
    source: str,
    recorded: str,
    created: str,
) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO activity_events(
            event_key, github_user, kind, points, source, title, url, created_at, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item.key,
            github_user,
            item.kind,
            item.points,
            source,
            item.title,
            item.url,
            created,
            recorded,
        ),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        return False
    row = conn.execute(
        "SELECT points, badges FROM links WHERE github_user = ?", (github_user,)
    ).fetchone()
    if row is None:
        conn.rollback()
        return False
    new_points = int(row["points"]) + item.points
    badges = merge_badges(tuple(json.loads(row["badges"] or "[]")), new_points)
    conn.execute(
        "UPDATE links SET points = ?, badges = ?, updated_at = ? WHERE github_user = ?",
        (new_points, json.dumps(badges), recorded, github_user),
    )
    conn.commit()
    return True
