"""Command parsing that accepts friendly English, Chinese and Japanese aliases."""

from __future__ import annotations

from dataclasses import dataclass

COMMAND_ALIASES: dict[str, str] = {
    # onboarding
    "start": "start",
    "welcome": "start",
    "开始": "start",
    "はじめ": "start",
    "はじめに": "start",
    # help
    "help": "help",
    "帮助": "help",
    "ヘルプ": "help",
    # link
    "link": "link",
    "link_github": "link",
    "bind": "link",
    "绑定": "link",
    "連携": "link",
    # challenge
    "challenge": "challenge",
    "my_challenge": "challenge",
    "挑战": "challenge",
    "チャレンジ": "challenge",
    # leaderboard
    "leaderboard": "leaderboard",
    "lb": "leaderboard",
    "排行": "leaderboard",
    "排行榜": "leaderboard",
    "ランキング": "leaderboard",
    # sentiment
    "sentiment": "sentiment",
    "tone": "sentiment",
    "语气": "sentiment",
    "感情": "sentiment",
    "トーン": "sentiment",
    # ask / chat
    "ask": "ask",
    "chat": "ask",
    "问": "ask",
    "質問": "ask",
    # language
    "language": "language",
    "lang": "language",
    "语言": "language",
    "言語": "language",
    # privacy
    "privacy": "privacy",
    "data": "privacy",
    "隐私": "privacy",
    "プライバシー": "privacy",
    # status
    "status": "status",
    "状态": "status",
    "ステータス": "status",
    # about
    "about": "about",
    "关于": "about",
    "概要": "about",
    # admin
    "set_repo": "set_repo",
    "setrepo": "set_repo",
    "repo": "set_repo",
    "仓库": "set_repo",
    "リポジトリ": "set_repo",
    "refresh": "refresh",
    "update_stats": "refresh",
    "更新": "refresh",
    "shutdown": "shutdown",
    "关机": "shutdown",
    "停止": "shutdown",
    "unlink": "unlink",
    "解除": "unlink",
}


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    name: str
    args: str
    raw: str


def normalize_command(token: str) -> str | None:
    token = token.strip().lower().replace("-", "_")
    if not token:
        return None
    return COMMAND_ALIASES.get(token) or (token if token in COMMAND_ALIASES.values() else None)


def parse_command(text: str, prefixes: tuple[str, ...]) -> ParsedCommand | None:
    stripped = text.strip()
    if not stripped:
        return None
    prefix = next((candidate for candidate in prefixes if stripped.startswith(candidate)), None)
    if prefix is None:
        return None
    remainder = stripped[len(prefix) :].lstrip()
    if not remainder:
        return None
    token, _, args = remainder.partition(" ")
    # Telegram appends @BotName to commands.
    token = token.split("@", 1)[0]
    name = normalize_command(token) or token.lower().replace("-", "_")
    if not name:
        return None
    return ParsedCommand(name=name, args=args.strip(), raw=stripped)


def strip_bot_mention(text: str, bot_user_id: str | None = None) -> tuple[str, bool]:
    """Remove leading Discord/Slack-style mentions and report whether one existed."""

    mentioned = False
    value = text.strip()
    if bot_user_id:
        for pattern in (f"<@{bot_user_id}>", f"<@!{bot_user_id}>"):
            if value.startswith(pattern):
                value = value[len(pattern) :].lstrip()
                mentioned = True
                break
    # A generic leading mention is useful for bridges that cannot resolve names.
    if value.startswith("<@") and ">" in value:
        value = value.split(">", 1)[1].lstrip()
        mentioned = True
    return value, mentioned
