#!/usr/bin/env python3
"""Import a v1 GitHub-Discord-Bot ``user_data.db`` into the v2 schema.

Stop the v2 bot before running this. The target database is created if needed.
The import is idempotent for members and links; it never lowers an existing score.

    python scripts/import_v1.py --legacy user_data.db --database data/community.db --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from github_community_bot.storage import Database  # noqa: E402


def read_legacy(path: Path) -> list[tuple[str, str, int]]:
    if not path.exists():
        raise SystemExit(f"Legacy database not found: {path}")
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "users" not in tables:
            raise SystemExit("Legacy database has no 'users' table")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
        required = {"discord_id", "github_user", "points"}
        missing = required - columns
        if missing:
            raise SystemExit(f"Legacy users table is missing columns: {sorted(missing)}")
        rows = []
        for row in connection.execute("SELECT discord_id, github_user, points FROM users"):
            discord_id = str(row["discord_id"] or "").strip()
            github_user = str(row["github_user"] or "").strip().lstrip("@")
            points = max(0, int(row["points"] or 0))
            if discord_id and github_user:
                rows.append((discord_id, github_user, points))
        return rows
    finally:
        connection.close()


async def import_rows(
    rows: list[tuple[str, str, int]], database: Path, platform: str
) -> dict[str, int]:
    db = Database(database)
    await db.connect()
    stats = {"members": 0, "new_links": 0, "merged_links": 0, "skipped": 0}
    try:
        for discord_id, github_user, points in rows:
            await db.touch_member(platform, discord_id, github_user)
            existing = await db.get_link(github_user)
            try:
                link, created = await db.link_member(
                    platform, discord_id, github_user, baseline_points=points
                )
            except Exception as exc:  # e.g. a chat identity already linked elsewhere
                stats["skipped"] += 1
                print(f"  skip {discord_id} -> {github_user}: {exc}")
                continue
            if created:
                stats["new_links"] += 1
            else:
                stats["merged_links"] += 1
                if existing and existing.points < points:
                    link = await db.ensure_minimum_points(github_user, points) or link
                print(
                    f"  merge {discord_id} -> {github_user}: "
                    f"shared score {link.points if link else '?'}"
                )
            stats["members"] += 1
        return stats
    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", default="user_data.db", type=Path)
    parser.add_argument("--database", default=Path("data/community.db"), type=Path)
    parser.add_argument("--platform", default="discord")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = read_legacy(args.legacy)
    print(f"Found {len(rows)} linked users in {args.legacy}")
    if args.dry_run:
        for discord_id, github_user, points in rows[:20]:
            print(f"  {discord_id} -> {github_user} ({points} pts)")
        if len(rows) > 20:
            print(f"  … and {len(rows) - 20} more")
        print("Dry run: target database was not modified.")
        return 0

    if args.database.exists():
        print(f"Target exists: {args.database}")
        print("Make a backup first. Existing scores are never lowered.")
    else:
        print(f"Creating target: {args.database}")

    stats = asyncio.run(import_rows(rows, args.database, args.platform))
    print(
        "Done. Members: {members}, new links: {new_links}, "
        "merged links: {merged_links}, skipped: {skipped}".format(**stats)
    )
    print("Start the bot and run !set_repo owner/repo, then !leaderboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
