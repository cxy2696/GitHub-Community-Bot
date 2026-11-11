from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from github_community_bot.config import GitHubConfig
from github_community_bot.services.github import ActivityCounts, GitHubService


class FakePaginated:
    def __init__(self, items):
        self._items = items
        self.totalCount = len(items)

    def __iter__(self):
        return iter(self._items)


class FakeRepo:
    full_name = "owner/repo"
    description = "A repo"
    private = False
    html_url = "https://github.com/owner/repo"

    def __init__(self):
        self.commits = []
        self.issues = []

    def get_commits(self, **kwargs):
        return FakePaginated(self.commits)

    def get_issues(self, **kwargs):
        return FakePaginated(self.issues)


class FakeClient:
    def __init__(self):
        self.counts = {"issue": 2, "pr": 1}

    def search_issues(self, query):
        count = self.counts["issue"] if "is:issue" in query else self.counts["pr"]
        return SimpleNamespace(totalCount=count)


def make_commit(sha: str):
    created = datetime(2026, 11, 11, tzinfo=UTC)
    return SimpleNamespace(
        sha=sha,
        html_url=f"https://github.com/owner/repo/commit/{sha}",
        commit=SimpleNamespace(
            message="Fix the docs\n\nDetails",
            author=SimpleNamespace(date=created),
        ),
    )


def make_issue(number: int, is_pr: bool, login: str = "Alice"):
    created = datetime(2026, 11, 11, tzinfo=UTC)
    return SimpleNamespace(
        number=number,
        title="A change",
        html_url=f"https://github.com/owner/repo/issues/{number}",
        created_at=created,
        user=SimpleNamespace(login=login),
        raw_data={"pull_request": {"url": "..."}} if is_pr else {},
    )


def test_activity_counts_points():
    assert ActivityCounts(commits=3, issues=2, prs=1).points == 100


def test_recent_activity_normalizes_commit_issue_and_pr():
    service = GitHubService(GitHubConfig(repo="owner/repo"))
    repo = FakeRepo()
    repo.commits = [make_commit("abc")]
    repo.issues = [make_issue(1, is_pr=False), make_issue(2, is_pr=True)]
    service._repo = repo  # type: ignore[assignment]
    since = datetime(2026, 11, 1, tzinfo=UTC)
    items = asyncio.run(service.recent_activity("Alice", since))
    kinds = {item.kind for item in items}
    assert kinds == {"commit", "issue", "pull_request"}
    assert {item.key for item in items} == {
        "commit:owner/repo:abc",
        "issue:owner/repo:1",
        "pr:owner/repo:2",
    }
    assert all(item.points > 0 for item in items)


def test_get_totals_caches_results():
    service = GitHubService(GitHubConfig(repo="owner/repo"))
    repo = FakeRepo()
    repo.commits = [make_commit("a"), make_commit("b")]
    service._repo = repo  # type: ignore[assignment]
    service._client = FakeClient()  # type: ignore[assignment]

    async def run():
        first = await service.get_totals("Alice")
        second = await service.get_totals("alice")
        return first, second

    first, second = asyncio.run(run())
    assert first == ActivityCounts(commits=2, issues=2, prs=1)
    assert second is first


def test_health_without_repo():
    service = GitHubService(GitHubConfig())
    assert asyncio.run(service.health()) == ("not_configured", "No repository selected")
