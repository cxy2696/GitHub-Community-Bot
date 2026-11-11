"""Discord adapter with modern slash commands and classic prefixed messages."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ..commands import strip_bot_mention
from ..config import DiscordConfig
from ..models import IncomingMessage, Reply
from .base import PlatformAdapter, chunk_text

if TYPE_CHECKING:  # pragma: no cover
    from ..bot import CommunityBot

logger = logging.getLogger(__name__)


class DiscordAdapter(PlatformAdapter):
    name = "discord"

    def __init__(self, config: DiscordConfig) -> None:
        super().__init__()
        self.config = config
        self.client: discord.Client | None = None
        self.tree: app_commands.CommandTree | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self, bot: CommunityBot) -> None:
        self.bot = bot
        assert self.config.token is not None
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        self._register_slash_commands()
        self.client.on_message = self._on_message  # type: ignore[method-assign]
        self.client.on_ready = self._on_ready  # type: ignore[method-assign]
        self._task = asyncio.create_task(self._run(), name="discord-adapter")
        self._task.add_done_callback(self._task_done)

    async def _run(self) -> None:
        assert self.client is not None
        await self.client.start(self.config.token or "")

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self.ready = False
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Discord adapter stopped with an error")

    async def stop(self) -> None:
        self.ready = False
        if self.client is not None:
            await self.client.close()
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _on_ready(self) -> None:
        self.ready = True
        assert self.client is not None and self.client.user is not None
        logger.info("Discord connected as %s", self.client.user)
        if self.config.sync_commands and self.tree is not None:
            try:
                synced = await self.tree.sync()
                logger.info("Synced %s Discord slash commands", len(synced))
            except Exception as exc:
                logger.warning("Could not sync Discord slash commands: %s", exc)

    async def _on_message(self, message: discord.Message) -> None:
        if message.author.bot or self.bot is None or self.client is None:
            return
        if (
            message.guild is not None
            and self.config.channel_ids
            and str(message.channel.id) not in self.config.channel_ids
        ):
            return

        mentioned = bool(self.client.user and self.client.user in message.mentions)
        text, _ = strip_bot_mention(
            message.content, str(self.client.user.id) if self.client.user else None
        )
        has_prefix = any(text.startswith(prefix) for prefix in self.bot.config.command_prefixes)
        is_dm = message.guild is None
        if not (is_dm or mentioned or has_prefix):
            return

        incoming = IncomingMessage(
            platform=self.name,
            channel_id=str(message.channel.id),
            user_id=str(message.author.id),
            user_name=getattr(message.author, "display_name", message.author.name),
            text=text,
            message_id=str(message.id),
            is_dm=is_dm,
            mentions_bot=mentioned,
            is_admin=str(message.author.id) in self.config.admin_ids,
            locale_hint=str(message.guild.preferred_locale) if message.guild else None,
        )
        try:
            async with message.channel.typing():
                replies = await self.bot.handle_message(incoming)
        except Exception:
            logger.exception("Discord message handling failed")
            return
        for reply in replies:
            for index, chunk in enumerate(chunk_text(reply.text, 1900)):
                try:
                    if index == 0 and (is_dm or mentioned):
                        await message.reply(chunk, mention_author=False)
                    else:
                        await message.channel.send(chunk)
                except Exception:
                    logger.exception("Could not send Discord reply")
                    break

    async def deliver(self, channel_id: str, reply: Reply, *, thread_id: str | None = None) -> None:
        if self.client is None:
            return
        channel = self.client.get_channel(int(channel_id))
        if channel is None:
            channel = await self.client.fetch_channel(int(channel_id))
        for chunk in chunk_text(reply.text, 1900):
            await channel.send(chunk)  # type: ignore[union-attr]

    # ------------------------------------------------------------- slash commands

    def _register_slash_commands(self) -> None:
        assert self.tree is not None
        tree = self.tree

        @tree.command(name="help", description="Show what I can do")
        async def help_command(interaction: discord.Interaction) -> None:
            await self._slash(interaction, "help")

        @tree.command(name="start", description="A quick tour of the bot")
        async def start_command(interaction: discord.Interaction) -> None:
            await self._slash(interaction, "start")

        @tree.command(name="challenge", description="Get one personalized next step")
        async def challenge_command(interaction: discord.Interaction) -> None:
            await self._slash(interaction, "challenge")

        @tree.command(name="leaderboard", description="See the community leaderboard")
        async def leaderboard_command(interaction: discord.Interaction) -> None:
            await self._slash(interaction, "leaderboard")

        @tree.command(name="link", description="Connect your GitHub account")
        @app_commands.describe(github_username="Your GitHub username, not display name")
        async def link_command(interaction: discord.Interaction, github_username: str) -> None:
            await self._slash(interaction, f"link {github_username}", ephemeral=True)

        @tree.command(name="ask", description="Ask the local Ollama model a question")
        @app_commands.describe(question="A short question")
        async def ask_command(interaction: discord.Interaction, question: str) -> None:
            await self._slash(interaction, f"ask {question}")

        @tree.command(name="sentiment", description="Reflect on the tone of a message")
        @app_commands.describe(text="The message or tone you want to reflect on")
        async def sentiment_command(interaction: discord.Interaction, text: str) -> None:
            await self._slash(interaction, f"sentiment {text}")

        @tree.command(name="language", description="Choose English, Chinese or Japanese")
        @app_commands.choices(
            language=[
                app_commands.Choice(name="English", value="en"),
                app_commands.Choice(name="中文", value="zh"),
                app_commands.Choice(name="日本語", value="ja"),
            ]
        )
        async def language_command(
            interaction: discord.Interaction, language: app_commands.Choice[str]
        ) -> None:
            await self._slash(interaction, f"language {language.value}", ephemeral=True)

        @tree.command(name="privacy", description="See, opt out of, or delete your data")
        @app_commands.choices(
            action=[
                app_commands.Choice(name="What do you store?", value="status"),
                app_commands.Choice(name="Opt out", value="optout"),
                app_commands.Choice(name="Opt in", value="optin"),
                app_commands.Choice(name="Delete my data", value="delete-confirm"),
            ]
        )
        async def privacy_command(
            interaction: discord.Interaction, action: app_commands.Choice[str] | None = None
        ) -> None:
            if action is None or action.value == "status":
                text = "privacy"
            elif action.value == "delete-confirm":
                text = "privacy delete confirm"
            else:
                text = f"privacy {action.value}"
            await self._slash(interaction, text, ephemeral=True)

        @tree.command(name="status", description="Show bot health and uptime")
        async def status_command(interaction: discord.Interaction) -> None:
            await self._slash(interaction, "status", ephemeral=True)

    async def _slash(
        self, interaction: discord.Interaction, command_text: str, *, ephemeral: bool = False
    ) -> None:
        if self.bot is None:
            return
        try:
            await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        except Exception:
            logger.debug("Discord interaction was already acknowledged")
        incoming = IncomingMessage(
            platform=self.name,
            channel_id=str(interaction.channel_id or "dm"),
            user_id=str(interaction.user.id),
            user_name=getattr(interaction.user, "display_name", interaction.user.name),
            text=f"{self.bot.config.command_prefixes[0]}{command_text}",
            message_id=f"slash:{interaction.id}",
            is_dm=interaction.guild is None,
            mentions_bot=False,
            is_admin=str(interaction.user.id) in self.config.admin_ids,
            locale_hint=str(interaction.locale),
        )
        try:
            replies = await self.bot.handle_message(incoming)
        except Exception:
            logger.exception("Discord slash command failed")
            await interaction.followup.send(
                "Something went wrong. Please try again.", ephemeral=True
            )
            return
        for reply in replies:
            for chunk in chunk_text(reply.text, 1900):
                await interaction.followup.send(chunk, ephemeral=ephemeral or reply.ephemeral)
