"""Tests for Discord bot message filtering (DISCORD_ALLOW_BOTS)."""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_author(*, bot: bool = False, is_self: bool = False):
    """Create a mock Discord author."""
    author = MagicMock()
    author.bot = bot
    author.id = 99999 if is_self else 12345
    author.name = "TestBot" if bot else "TestUser"
    author.display_name = author.name
    return author


def _make_message(*, author=None, content="hello", mentions=None, is_dm=False):
    """Create a mock Discord message."""
    msg = MagicMock()
    msg.author = author or _make_author()
    msg.content = content
    msg.attachments = []
    msg.mentions = mentions or []
    if is_dm:
        import discord
        msg.channel = MagicMock(spec=discord.DMChannel)
        msg.channel.id = 111
    else:
        msg.channel = MagicMock()
        msg.channel.id = 222
        msg.channel.name = "test-channel"
        msg.channel.guild = MagicMock()
        msg.channel.guild.name = "TestServer"
        # Make isinstance checks fail for DMChannel and Thread
        type(msg.channel).__name__ = "TextChannel"
    return msg


class TestDiscordBotFilter(unittest.IsolatedAsyncioTestCase):
    """Test the DISCORD_ALLOW_BOTS filtering logic."""

    def _run_filter(self, message, allow_bots="none", client_user=None):
        """Simulate the on_message filter logic and return whether message was accepted."""
        # Replicate the exact filter logic from discord.py on_message
        if message.author == client_user:
            return False  # own messages always ignored

        if getattr(message.author, "bot", False):
            allow = allow_bots.lower().strip()
            if allow == "none":
                return False
            elif allow == "mentions":
                if not client_user or client_user not in message.mentions:
                    return False
            # "all" falls through
        
        return True  # message accepted

    def test_own_messages_always_ignored(self):
        """Bot's own messages are always ignored regardless of allow_bots."""
        bot_user = _make_author(is_self=True)
        msg = _make_message(author=bot_user)
        self.assertFalse(self._run_filter(msg, "all", bot_user))

    def test_human_messages_always_accepted(self):
        """Human messages are always accepted regardless of allow_bots."""
        human = _make_author(bot=False)
        msg = _make_message(author=human)
        self.assertTrue(self._run_filter(msg, "none"))
        self.assertTrue(self._run_filter(msg, "mentions"))
        self.assertTrue(self._run_filter(msg, "all"))

    def test_allow_bots_none_rejects_bots(self):
        """With allow_bots=none, all other bot messages are rejected."""
        bot = _make_author(bot=True)
        msg = _make_message(author=bot)
        self.assertFalse(self._run_filter(msg, "none"))

    def test_allow_bots_all_accepts_bots(self):
        """With allow_bots=all, all bot messages are accepted."""
        bot = _make_author(bot=True)
        msg = _make_message(author=bot)
        self.assertTrue(self._run_filter(msg, "all"))

    def test_allow_bots_mentions_rejects_without_mention(self):
        """With allow_bots=mentions, bot messages without @mention are rejected."""
        our_user = _make_author(is_self=True)
        bot = _make_author(bot=True)
        msg = _make_message(author=bot, mentions=[])
        self.assertFalse(self._run_filter(msg, "mentions", our_user))

    def test_allow_bots_mentions_accepts_with_mention(self):
        """With allow_bots=mentions, bot messages with @mention are accepted."""
        our_user = _make_author(is_self=True)
        bot = _make_author(bot=True)
        msg = _make_message(author=bot, mentions=[our_user])
        self.assertTrue(self._run_filter(msg, "mentions", our_user))

    def test_default_is_none(self):
        """Default behavior (no env var) should be 'none'."""
        with patch.dict(os.environ, {}, clear=True):
            default = os.getenv("DISCORD_ALLOW_BOTS", "none")
            self.assertEqual(default, "none")

    def test_case_insensitive(self):
        """Allow_bots value should be case-insensitive."""
        bot = _make_author(bot=True)
        msg = _make_message(author=bot)
        self.assertTrue(self._run_filter(msg, "ALL"))
        self.assertTrue(self._run_filter(msg, "All"))
        self.assertFalse(self._run_filter(msg, "NONE"))
        self.assertFalse(self._run_filter(msg, "None"))

    def test_trusted_agent_user_ids_default_to_known_private_agents(self):
        """Mia admits known Yomi and Sion bot IDs by default."""
        from gateway.platforms.discord import _discord_trusted_agent_user_ids

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                _discord_trusted_agent_user_ids(),
                {"1493785569602441337", "1500372119744413817"},
            )

    def test_trusted_agent_user_ids_can_be_disabled(self):
        """Operators can disable the trusted-agent bypass explicitly."""
        from gateway.platforms.discord import _discord_trusted_agent_user_ids

        with patch.dict(os.environ, {"DISCORD_TRUSTED_AGENT_USER_IDS": "none"}, clear=True):
            self.assertEqual(_discord_trusted_agent_user_ids(), set())

    def test_trusted_agent_user_ids_accept_mention_syntax(self):
        """Discord mention syntax is normalized to bare IDs."""
        from gateway.platforms.discord import _discord_trusted_agent_user_ids

        with patch.dict(
            os.environ,
            {"DISCORD_TRUSTED_AGENT_USER_IDS": "<@1500372119744413817>"},
            clear=True,
        ):
            self.assertEqual(_discord_trusted_agent_user_ids(), {"1500372119744413817"})

    def test_legacy_yomi_user_ids_still_work(self):
        """The older Yomi-only config remains a compatibility path."""
        from gateway.platforms.discord import _discord_trusted_agent_user_ids

        with patch.dict(os.environ, {"DISCORD_YOMI_USER_IDS": "<@1493785569602441337>"}, clear=True):
            self.assertEqual(_discord_trusted_agent_user_ids(), {"1493785569602441337"})

    def test_trusted_agent_channel_ids_default_to_mia_yomi_coord(self):
        """The dedicated Mia/Yomi coordination channel is relaxed by default."""
        from gateway.platforms.discord import _discord_trusted_agent_channel_ids

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_discord_trusted_agent_channel_ids(), {"1507957383203389521"})

    def test_trusted_agent_channel_ids_can_be_disabled(self):
        """Operators can disable coordination-channel relaxation explicitly."""
        from gateway.platforms.discord import _discord_trusted_agent_channel_ids

        with patch.dict(os.environ, {"DISCORD_TRUSTED_AGENT_CHANNEL_IDS": "none"}, clear=True):
            self.assertEqual(_discord_trusted_agent_channel_ids(), set())

    def test_trusted_agent_channel_ids_accept_mention_syntax(self):
        """Channel mention syntax is normalized to bare IDs."""
        from gateway.platforms.discord import _discord_trusted_agent_channel_ids

        with patch.dict(
            os.environ,
            {"DISCORD_TRUSTED_AGENT_CHANNEL_IDS": "<#1507957383203389521>"},
            clear=True,
        ):
            self.assertEqual(_discord_trusted_agent_channel_ids(), {"1507957383203389521"})

    def test_trusted_agent_guidance_exact_bot_match(self):
        """Only configured bot authors are classified as trusted guidance."""
        from gateway.platforms.discord import DiscordAdapter

        adapter = object.__new__(DiscordAdapter)
        adapter._trusted_agent_user_ids = {"1493785569602441337", "1500372119744413817"}

        yomi = _make_author(bot=True)
        yomi.id = 1493785569602441337
        sion = _make_author(bot=True)
        sion.id = 1500372119744413817
        other_bot = _make_author(bot=True)
        other_bot.id = 999888777

        self.assertTrue(adapter._is_trusted_agent_guidance_message(_make_message(author=yomi)))
        self.assertTrue(adapter._is_trusted_agent_guidance_message(_make_message(author=sion)))
        self.assertFalse(adapter._is_trusted_agent_guidance_message(_make_message(author=other_bot)))
        self.assertFalse(
            adapter._is_trusted_agent_guidance_message(_make_message(author=_make_author(bot=False)))
        )

    async def test_trusted_agent_reply_to_self_is_suppressed(self):
        """Replies from trusted agents to Mia's own message are loop-suppressed."""
        from gateway.platforms.discord import DiscordAdapter

        adapter = object.__new__(DiscordAdapter)
        adapter._client = MagicMock()
        adapter._client.user = _make_author(bot=True, is_self=True)

        reply_author = _make_author(bot=True, is_self=True)
        replied = MagicMock()
        replied.author = reply_author
        msg = _make_message(author=_make_author(bot=True))
        msg.reference = MagicMock()
        msg.reference.resolved = replied

        self.assertTrue(await adapter._reply_targets_client_user(msg))

    async def test_trusted_agent_guidance_bypasses_channel_mention_gate(self):
        """Trusted private-agent guidance should reach Mia without an @mention."""
        import discord

        from gateway.config import PlatformConfig
        from gateway.platforms.discord import DiscordAdapter

        adapter = DiscordAdapter(PlatformConfig(enabled=True, token="test-token"))
        adapter._client = MagicMock()
        adapter._client.user = _make_author(bot=True, is_self=True)
        adapter._trusted_agent_user_ids = {"1493785569602441337"}
        adapter._voice_text_channels = {}
        adapter._threads = MagicMock()
        adapter._threads.__contains__.return_value = False
        adapter._resolve_channel_skills = MagicMock(return_value=None)
        adapter._resolve_channel_prompt = MagicMock(return_value=None)
        adapter._get_effective_topic = MagicMock(return_value=None)
        adapter._auto_create_thread = AsyncMock(return_value=None)
        adapter.handle_message = AsyncMock()
        adapter._text_batch_delay_seconds = 0

        author = _make_author(bot=True)
        author.id = 1493785569602441337
        author.display_name = "Yomi"
        msg = _make_message(author=author, content="Mia, proceed with the task.", mentions=[])
        msg.type = discord.MessageType.default
        msg.reference = None
        msg.created_at = None
        msg.guild = msg.channel.guild

        with patch.dict(
            os.environ,
            {
                "DISCORD_REQUIRE_MENTION": "true",
                "DISCORD_TRUSTED_AGENT_REQUIRE_MENTION": "false",
            },
            clear=False,
        ):
            await adapter._handle_message(msg)

        adapter.handle_message.assert_awaited_once()
        adapter._auto_create_thread.assert_not_awaited()
        event = adapter.handle_message.await_args.args[0]
        self.assertEqual(event.text, "Mia, proceed with the task.")
        self.assertTrue(event.source.is_bot)
        self.assertEqual(event.source.user_id, "1493785569602441337")

    def test_trusted_agent_require_mention_config(self):
        """Operators can require trusted-agent messages to explicitly mention this bot."""
        from gateway.config import PlatformConfig
        from gateway.platforms.discord import DiscordAdapter

        adapter = DiscordAdapter(
            PlatformConfig(
                enabled=True,
                token="test-token",
                extra={"trusted_agent_require_mention": True},
            )
        )

        self.assertTrue(adapter._discord_trusted_agent_require_mention())

    async def test_trusted_agent_guidance_can_require_mention(self):
        """When enabled, trusted-agent guidance without a mention is suppressed."""
        import discord

        from gateway.config import PlatformConfig
        from gateway.platforms.discord import DiscordAdapter

        adapter = DiscordAdapter(
            PlatformConfig(
                enabled=True,
                token="test-token",
                extra={"trusted_agent_require_mention": True},
            )
        )
        adapter._client = MagicMock()
        adapter._client.user = _make_author(bot=True, is_self=True)
        adapter._trusted_agent_user_ids = {"1493785569602441337"}
        adapter._reply_targets_client_user = AsyncMock(return_value=False)
        adapter._audit_trusted_agent_guidance = MagicMock()
        adapter.handle_message = AsyncMock()

        author = _make_author(bot=True)
        author.id = 1493785569602441337
        author.display_name = "Yomi"
        msg = _make_message(author=author, content="coordination note", mentions=[])
        msg.type = discord.MessageType.default
        msg.reference = None

        await adapter._handle_message(msg)

        adapter.handle_message.assert_not_awaited()
        adapter._reply_targets_client_user.assert_not_awaited()
        adapter._audit_trusted_agent_guidance.assert_called_once()
        self.assertEqual(
            adapter._audit_trusted_agent_guidance.call_args.args[2],
            "trusted_agent_requires_mention",
        )

    async def test_trusted_agent_coord_channel_bypasses_require_mention_gate(self):
        """Dedicated coordination channels admit trusted agents without mention."""
        import discord

        from gateway.config import PlatformConfig
        from gateway.platforms.discord import DiscordAdapter

        adapter = DiscordAdapter(
            PlatformConfig(
                enabled=True,
                token="test-token",
                extra={
                    "trusted_agent_require_mention": True,
                    "trusted_agent_channel_ids": ["1507957383203389521"],
                },
            )
        )
        adapter._client = MagicMock()
        adapter._client.user = _make_author(bot=True, is_self=True)
        adapter._trusted_agent_user_ids = {"1493785569602441337"}
        adapter._trusted_agent_channel_ids = {"1507957383203389521"}
        adapter._voice_text_channels = {}
        adapter._threads = MagicMock()
        adapter._threads.__contains__.return_value = False
        adapter._resolve_channel_skills = MagicMock(return_value=None)
        adapter._resolve_channel_prompt = MagicMock(return_value=None)
        adapter._get_effective_topic = MagicMock(return_value=None)
        adapter._auto_create_thread = AsyncMock(return_value=None)
        adapter._audit_trusted_agent_guidance = MagicMock()
        adapter.handle_message = AsyncMock()
        adapter._text_batch_delay_seconds = 0

        author = _make_author(bot=True)
        author.id = 1493785569602441337
        author.display_name = "Yomi"
        msg = _make_message(author=author, content="coordination update", mentions=[])
        msg.channel.id = 1507957383203389521
        msg.type = discord.MessageType.default
        msg.reference = None
        msg.created_at = None
        msg.guild = msg.channel.guild

        with patch.dict(os.environ, {"DISCORD_REQUIRE_MENTION": "true"}, clear=False):
            await adapter._handle_message(msg)

        adapter.handle_message.assert_awaited_once()
        adapter._audit_trusted_agent_guidance.assert_not_called()
        event = adapter.handle_message.await_args.args[0]
        self.assertEqual(event.text, "coordination update")
        self.assertTrue(event.source.is_bot)
        self.assertEqual(event.source.chat_id, "1507957383203389521")

    async def test_trusted_agent_non_coord_channel_still_requires_mention(self):
        """The coordination-channel relaxation does not leak to other channels."""
        import discord

        from gateway.config import PlatformConfig
        from gateway.platforms.discord import DiscordAdapter

        adapter = DiscordAdapter(
            PlatformConfig(
                enabled=True,
                token="test-token",
                extra={
                    "trusted_agent_require_mention": True,
                    "trusted_agent_channel_ids": ["1507957383203389521"],
                },
            )
        )
        adapter._client = MagicMock()
        adapter._client.user = _make_author(bot=True, is_self=True)
        adapter._trusted_agent_user_ids = {"1493785569602441337"}
        adapter._trusted_agent_channel_ids = {"1507957383203389521"}
        adapter._audit_trusted_agent_guidance = MagicMock()
        adapter.handle_message = AsyncMock()

        author = _make_author(bot=True)
        author.id = 1493785569602441337
        msg = _make_message(author=author, content="coordination update", mentions=[])
        msg.channel.id = 222
        msg.type = discord.MessageType.default
        msg.reference = None

        await adapter._handle_message(msg)

        adapter.handle_message.assert_not_awaited()
        adapter._audit_trusted_agent_guidance.assert_called_once()
        self.assertEqual(
            adapter._audit_trusted_agent_guidance.call_args.args[2],
            "trusted_agent_requires_mention",
        )

    async def test_trusted_agent_direct_address_passes_require_mention_gate(self):
        """A trusted agent can address Mia by name without a Discord mention."""
        import discord

        from gateway.config import PlatformConfig
        from gateway.platforms.discord import DiscordAdapter

        adapter = DiscordAdapter(
            PlatformConfig(
                enabled=True,
                token="test-token",
                extra={"trusted_agent_require_mention": True},
            )
        )
        adapter._client = MagicMock()
        adapter._client.user = _make_author(bot=True, is_self=True)
        adapter._trusted_agent_user_ids = {"1493785569602441337"}
        adapter._voice_text_channels = {}
        adapter._threads = MagicMock()
        adapter._threads.__contains__.return_value = False
        adapter._resolve_channel_skills = MagicMock(return_value=None)
        adapter._resolve_channel_prompt = MagicMock(return_value=None)
        adapter._get_effective_topic = MagicMock(return_value=None)
        adapter._auto_create_thread = AsyncMock(return_value=None)
        adapter._audit_trusted_agent_guidance = MagicMock()
        adapter.handle_message = AsyncMock()
        adapter._text_batch_delay_seconds = 0

        author = _make_author(bot=True)
        author.id = 1493785569602441337
        author.display_name = "Yomi"
        msg = _make_message(author=author, content="ミア、次のタスクを確認して", mentions=[])
        msg.type = discord.MessageType.default
        msg.reference = None
        msg.created_at = None
        msg.guild = msg.channel.guild

        with patch.dict(os.environ, {"DISCORD_REQUIRE_MENTION": "true"}, clear=False):
            await adapter._handle_message(msg)

        adapter.handle_message.assert_awaited_once()
        adapter._audit_trusted_agent_guidance.assert_not_called()
        event = adapter.handle_message.await_args.args[0]
        self.assertEqual(event.text, "次のタスクを確認して")
        self.assertTrue(event.source.is_bot)
        self.assertEqual(event.source.user_id, "1493785569602441337")

    async def test_trusted_agent_third_person_mia_does_not_pass_require_mention_gate(self):
        """Third-person trusted-agent chatter about Mia is still suppressed."""
        import discord

        from gateway.config import PlatformConfig
        from gateway.platforms.discord import DiscordAdapter

        adapter = DiscordAdapter(
            PlatformConfig(
                enabled=True,
                token="test-token",
                extra={"trusted_agent_require_mention": True},
            )
        )
        adapter._client = MagicMock()
        adapter._client.user = _make_author(bot=True, is_self=True)
        adapter._trusted_agent_user_ids = {"1493785569602441337"}
        adapter._audit_trusted_agent_guidance = MagicMock()
        adapter.handle_message = AsyncMock()

        author = _make_author(bot=True)
        author.id = 1493785569602441337
        msg = _make_message(author=author, content="Mia の判断は妥当です", mentions=[])
        msg.type = discord.MessageType.default
        msg.reference = None

        await adapter._handle_message(msg)

        adapter.handle_message.assert_not_awaited()
        adapter._audit_trusted_agent_guidance.assert_called_once()
        self.assertEqual(
            adapter._audit_trusted_agent_guidance.call_args.args[2],
            "trusted_agent_requires_mention",
        )


if __name__ == "__main__":
    unittest.main()
