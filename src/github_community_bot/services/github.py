"""GitHub integration with pagination limits and friendly error mapping."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from github import Auth, Github, GithubException

from ..config import GitHubConfig
from ..gamification import points_for
from ..models import ActivityItem

logger = logging.getLogger(__name__)


class GitHubError(RuntimeError):
    """A GitHub failure that is safe to translate into a user-facing message."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class ActivityCounts:
    commits: int
    issues: int
    prs: int

    @property
    def points(self) -> int:
        return (
            self.commits * points_for("commit")
            + self.issues * points_for("issue")
            + self.prs * points_for("pull_request")
        )


@dataclass(frozen=True, slots=True)
class RepoInfo:
    full_name: str
    description: str | None
    private: bool
    html_url: str


class GitHubService:
    def __init__(self, config: GitHubConfig) -> None:
        self.config = config
        kwargs: dict[str, object] = {
            "base_url": config.api_url,
            "timeout": config.request_timeout_seconds,
        }
        if config.token:
            kwargs["auth"] = Auth.Token(config.token)
        self._client = Github(**kwargs)  # type: ignore[arg-type]
        self._repo = None
        self._lock = asyncio.Lock()
        self._totals_cache: dict[str, tuple[float, ActivityCounts]] = {}

    @property
    def configured(self) -> bool:
        return bool(self.config.token)

    @property
    def repo_name(self) -> str | None:
        return self._repo.full_name if self._repo is not None else self.config.repo

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close:
            await asyncio.to_thread(close)

    async def _run(self, func, *args, **kwargs):
        async with self._lock:
            try:
                return await asyncio.to_thread(func, *args, **kwargs)
            except GithubException as exc:
                status = getattr(exc, "status", None)
                data = getattr(exc, "data", {}) or {}
                message = data.get("message") if isinstance(data, dict) else None
                logger.warning("GitHub API error %s: %s", status, message or exc)
                raise GitHubError(message or str(exc), status) from exc
            except Exception as exc:
                logger.warning("GitHub request failed: %s", exc)
                raise GitHubError(str(exc)) from exc

    async def validate(self) -> str | None:
        """Return the authenticated login, or ``None`` for anonymous access."""
        if not self.config.token:
            return None

        def _whoami() -> str:
            return self._client.get_user().login

        return await self._run(_whoami)

    async def select_repo(self, full_name: str) -> RepoInfo:
        def _get():
            repo = self._client.get_repo(full_name)
            return repo

        repo = await self._run(_get)
        self._repo = repo
        return RepoInfo(
            full_name=repo.full_name,
            description=repo.description,
            private=repo.private,
            html_url=repo.html_url,
        )

    @property
    def repository(self):
        if self._repo is None:
            if not self.config.repo:
                raise GitHubError("No repository selected")
            # Loading is intentionally synchronous here because every public
            # method wraps itself in _run; callers should use ensure_repo().
            raise GitHubError("Repository has not been loaded yet")
        return self._repo

    async def ensure_repo(self) -> None:
        if self._repo is not None:
            return
        if not self.config.repo:
            return
        await self.select_repo(self.config.repo)

    async def get_totals(self, github_user: str) -> ActivityCounts:
        repo = self.repository
        cache_key = github_user.lower()
        cached = self._totals_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 300:
            return cached[1]

        def _work() -> ActivityCounts:
            commits = int(repo.get_commits(author=github_user).totalCount)
            try:
                issues = int(
                    self._client.search_issues(
                        f"repo:{repo.full_name} is:issue author:{github_user}"
                    ).totalCount
                )
                prs = int(
                    self._client.search_issues(
                        f"repo:{repo.full_name} is:pr author:{github_user}"
                    ).totalCount
                )
            except GithubException:
                # Search has its own, smaller rate limit. A full scan is slower
                # but keeps one-time linking working when search is exhausted.
                issues = 0
                prs = 0
                for issue in repo.get_issues(creator=github_user, state="all"):
                    if issue.raw_data.get("pull_request"):
                        prs += 1
                    else:
                        issues += 1
            return ActivityCounts(commits=commits, issues=issues, prs=prs)

        result = await self._run(_work)
        self._totals_cache[cache_key] = (time.monotonic(), result)
        return result

    async def recent_activity(
        self, github_user: str, since: datetime, limit: int = 500
    ) -> list[ActivityItem]:
        """Return contributions created since ``since``.

        One issues call returns both issues and pull requests on GitHub, which
        keeps polling cheap for small and medium communities.
        """

        repo = self.repository
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        def _work() -> list[ActivityItem]:
            items: dict[str, ActivityItem] = {}
            for commit in repo.get_commits(author=github_user, since=since):
                if len(items) >= limit:
                    break
                commit_author = commit.commit.author
                created = commit_author.date if commit_author else None
                if created and created < since:
                    continue
                items[f"commit:{repo.full_name}:{commit.sha}"] = ActivityItem(
                    key=f"commit:{repo.full_name}:{commit.sha}",
                    kind="commit",
                    points=points_for("commit"),
                    title=(commit.commit.message or "").splitlines()[0][:200],
                    url=commit.html_url,
                    created_at=created,
                )

            seen_issues = 0
            for issue in repo.get_issues(
                creator=github_user, state="all", since=since, sort="created", direction="asc"
            ):
                if seen_issues >= limit:
                    break
                seen_issues += 1
                created = issue.created_at
                if created and created < since:
                    continue
                if (issue.user.login if issue.user else "").lower() != github_user.lower():
                    continue
                is_pr = bool(issue.raw_data.get("pull_request"))
                if is_pr:
                    key = f"pr:{repo.full_name}:{issue.number}"
                    items[key] = ActivityItem(
                        key=key,
                        kind="pull_request",
                        points=points_for("pull_request"),
                        title=issue.title[:200],
                        url=issue.html_url,
                        created_at=created,
                    )
                else:
                    key = f"issue:{repo.full_name}:{issue.number}"
                    items[key] = ActivityItem(
                        key=key,
                        kind="issue",
                        points=points_for("issue"),
                        title=issue.title[:200],
                        url=issue.html_url,
                        created_at=created,
                    )
            return sorted(items.values(), key=lambda item: item.created_at or since)

        return await self._run(_work)

    async def health(self) -> tuple[str, str]:
        """Return a (status, detail) tuple without raising."""

        if not self.repo_name:
            return "not_configured", "No repository selected"
        if not self.config.token:
            return "degraded", "Anonymous access (lower rate limit)"
        try:
            await self.ensure_repo()
            login = await self.validate()
            repo = self.repository.full_name
            if login:
                return "online", f"@{login} · {repo}"
            return "degraded", f"Anonymous access · {repo}"
        except GitHubError as exc:
            return "offline", str(exc)[:160]
