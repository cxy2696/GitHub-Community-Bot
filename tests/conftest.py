from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from github_community_bot.bot import CommunityBot
from github_community_bot.config import AppConfig, GitHubConfig, HttpConfig, Limits, OllamaConfig
from github_community_bot.i18n import I18n
from github_community_bot.metrics import Metrics
from github_community_bot.models import IncomingMessage
from github_community_bot.services.github import ActivityCounts, RepoInfo
from github_community_bot.storage import Database


class FakeAI:
    def __init__(self) -> None:
        self.failure = None
        self.answer_text = "A calm, useful answer."
        self.challenge_text = "Review one small PR and leave a kind comment."
        self.tone_text = "The tone sounds constructive, with one tense phrase."
        self.answers: list[str] = []

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health(self, force: bool = False):
        return "online", "fake model"

    async def answer(self, question: str, locale: str = "en", history=None) -> str:
        if self.failure:
            raise self.failure
        self.answers.append(question)
        return self.answer_text

    async def challenge(self, activity: str, locale: str = "en") -> str:
        if self.failure:
            raise self.failure
        return self.challenge_text

    async def reflect_tone(self, text: str, locale: str = "en") -> str:
        if self.failure:
            raise self.failure
        return self.tone_text


class FakeGitHub:
    repo_name = "cxy2696/GitHub-Discord-Bot"
    totals = ActivityCounts(commits=3, issues=2, prs=1)
    recent: list = []

    async def ensure_repo(self) -> None:
        return None

    async def get_totals(self, github_user: str) -> ActivityCounts:
        return self.totals

    async def recent_activity(self, github_user: str, since, limit: int = 500):
        return list(self.recent)

    async def select_repo(self, full_name: str) -> RepoInfo:
        self.repo_name = full_name
        return RepoInfo(full_name=full_name, description="", private=False, html_url="")

    async def health(self):
        return "online", "fake GitHub"

    async def validate(self):
        return "tester"

    async def close(self) -> None:
        return None


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        bot_name="Test Community Bot",
        database_path=tmp_path / "community.db",
        data_dir=tmp_path,
        http=HttpConfig(enabled=False),
        github=GitHubConfig(repo="cxy2696/GitHub-Discord-Bot"),
        ollama=OllamaConfig(model="test-model"),
        limits=Limits(rate_limit_per_minute=100, max_context_messages=6),
    )


@pytest.fixture
def i18n() -> I18n:
    return I18n()


@pytest.fixture
async def db(config: AppConfig):
    database = Database(config.database_path)
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def fake_ai() -> FakeAI:
    return FakeAI()


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def bot(config: AppConfig, db: Database, i18n: I18n, fake_ai: FakeAI, fake_github: FakeGitHub):
    return CommunityBot(config, db, i18n, fake_ai, fake_github, Metrics())


@pytest.fixture
def message_factory():
    counter = {"value": 0}

    def make(
        text: str,
        *,
        user_id: str = "u1",
        user_name: str = "Tester",
        platform: str = "discord",
        channel_id: str = "c1",
        is_dm: bool = True,
        is_admin: bool = False,
        mentions_bot: bool = False,
        locale_hint: str | None = "en",
    ) -> IncomingMessage:
        counter["value"] += 1
        return IncomingMessage(
            platform=platform,
            channel_id=channel_id,
            user_id=user_id,
            user_name=user_name,
            text=text,
            message_id=str(counter["value"]),
            is_dm=is_dm,
            mentions_bot=mentions_bot,
            is_admin=is_admin,
            locale_hint=locale_hint,
        )

    return make
