"""Tests for Discord bot message filtering (DISCORD_ALLOW_BOTS)."""

import os
import re
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


class TestDiscordBotFilter(unittest.TestCase):
    """Test the DISCORD_ALLOW_BOTS filtering logic."""

    @staticmethod
    def _self_is_explicitly_mentioned(message, client_user):
        """Mirror adapter._self_is_explicitly_mentioned: resolved or raw mention."""
        if not client_user:
            return False
        if client_user in message.mentions:
            return True
        raw_ids = {
            m.group(1)
            for m in re.finditer(r"<@!?(\d+)>", getattr(message, "content", "") or "")
        }
        return str(client_user.id) in raw_ids

    @staticmethod
    def _self_is_raw_mentioned(message, client_user):
        """Mirror adapter._self_is_raw_mentioned: raw inline token only."""
        if not client_user:
            return False
        raw_ids = {
            m.group(1)
            for m in re.finditer(r"<@!?(\d+)>", getattr(message, "content", "") or "")
        }
        return str(client_user.id) in raw_ids

    def _run_filter(
        self,
        message,
        allow_bots="none",
        client_user=None,
        bots_require_inline_mention=False,
    ):
        """Simulate the on_message filter logic and return whether message was accepted."""
        # Replicate the exact filter logic from discord.py on_message
        if message.author == client_user:
            return False  # own messages always ignored

        if getattr(message.author, "bot", False):
            allow = allow_bots.lower().strip()
            if allow == "none":
                return False
            elif allow == "mentions":
                if not self._self_is_explicitly_mentioned(message, client_user):
                    return False
            if (
                bots_require_inline_mention
                and not self._self_is_raw_mentioned(message, client_user)
            ):
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

    def test_allow_bots_mentions_accepts_with_raw_content_mention(self):
        """Raw <@!ID> mention counts even when message.mentions is empty."""
        our_user = _make_author(is_self=True)
        bot = _make_author(bot=True)
        msg = _make_message(author=bot, content=f"<@!{our_user.id}> relay", mentions=[])
        self.assertTrue(self._run_filter(msg, "mentions", our_user))

    def test_inline_mention_requirement_off_preserves_reply_ping_behavior(self):
        """Default behavior: resolved reply-ping mentions still admit bot messages."""
        our_user = _make_author(is_self=True)
        bot = _make_author(bot=True)
        msg = _make_message(author=bot, content="reply-ping only", mentions=[our_user])

        self.assertTrue(
            self._run_filter(
                msg,
                "all",
                our_user,
                bots_require_inline_mention=False,
            )
        )

    def test_inline_mention_requirement_rejects_reply_ping_only(self):
        """Opt-in guard rejects bot messages where only Discord's reply-ping mentions us."""
        our_user = _make_author(is_self=True)
        bot = _make_author(bot=True)
        msg = _make_message(author=bot, content="reply-ping only", mentions=[our_user])

        self.assertFalse(
            self._run_filter(
                msg,
                "all",
                our_user,
                bots_require_inline_mention=True,
            )
        )

    def test_inline_mention_requirement_accepts_body_mention(self):
        """Opt-in guard still admits intentional inline cross-bot mentions."""
        our_user = _make_author(is_self=True)
        bot = _make_author(bot=True)
        msg = _make_message(
            author=bot,
            content=f"<@{our_user.id}> intentional handoff",
            mentions=[our_user],
        )

        self.assertTrue(
            self._run_filter(
                msg,
                "all",
                our_user,
                bots_require_inline_mention=True,
            )
        )

    def test_inline_mention_requirement_does_not_affect_humans(self):
        """The opt-in guard only applies to bot-authored messages."""
        human = _make_author(bot=False)
        our_user = _make_author(is_self=True)
        msg = _make_message(author=human, content="human reply-ping", mentions=[our_user])

        self.assertTrue(
            self._run_filter(
                msg,
                "none",
                our_user,
                bots_require_inline_mention=True,
            )
        )

    def test_default_is_none(self):
        """Default behavior (no env var) should be 'none'."""
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


class TestTrustedAgentFilter(unittest.IsolatedAsyncioTestCase):
    def test_configured_ids_override_legacy_defaults(self):
        from plugins.platforms.discord.adapter import (
            _discord_trusted_agent_channel_ids,
            _discord_trusted_agent_user_ids,
        )

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                _discord_trusted_agent_user_ids(
                    {"trusted_agent_user_ids": ["<@123>", "456"]}
                ),
                {"123", "456"},
            )
            self.assertEqual(
                _discord_trusted_agent_channel_ids(
                    {"trusted_agent_channel_ids": ["<#789>"]}
                ),
                {"789"},
            )

    def test_trusted_agent_bypass_can_be_disabled(self):
        from plugins.platforms.discord.adapter import (
            _discord_trusted_agent_channel_ids,
            _discord_trusted_agent_user_ids,
        )

        with patch.dict(
            os.environ,
            {
                "DISCORD_TRUSTED_AGENT_USER_IDS": "none",
                "DISCORD_TRUSTED_AGENT_CHANNEL_IDS": "none",
            },
            clear=True,
        ):
            self.assertEqual(_discord_trusted_agent_user_ids(), set())
            self.assertEqual(_discord_trusted_agent_channel_ids(), set())

    def test_yaml_config_bridges_trusted_ids_for_gateway_auth(self):
        from plugins.platforms.discord.adapter import _apply_yaml_config

        with patch.dict(os.environ, {}, clear=True):
            seeded = _apply_yaml_config(
                {},
                {
                    "trusted_agent_user_ids": ["123", "456"],
                    "trusted_agent_channel_ids": ["789"],
                    "trusted_agent_require_mention": True,
                },
            )

            self.assertEqual(
                os.environ["DISCORD_TRUSTED_AGENT_USER_IDS"], "123,456"
            )
            self.assertEqual(
                os.environ["DISCORD_TRUSTED_AGENT_CHANNEL_IDS"], "789"
            )
            self.assertEqual(
                os.environ["DISCORD_TRUSTED_AGENT_REQUIRE_MENTION"], "true"
            )
            self.assertEqual(
                seeded["trusted_agent_user_ids"], ["123", "456"]
            )

    async def test_reply_to_own_message_is_detected(self):
        from plugins.platforms.discord.adapter import DiscordAdapter

        adapter = object.__new__(DiscordAdapter)
        adapter._client = MagicMock()
        adapter._client.user = _make_author(bot=True, is_self=True)
        replied = MagicMock()
        replied.author = adapter._client.user
        message = _make_message(author=_make_author(bot=True))
        message.reference = MagicMock(resolved=replied)

        self.assertTrue(await adapter._reply_targets_client_user(message))

    async def test_unresolved_reply_is_fetched_for_loop_detection(self):
        from plugins.platforms.discord.adapter import DiscordAdapter

        adapter = object.__new__(DiscordAdapter)
        adapter._client = MagicMock()
        adapter._client.user = _make_author(bot=True, is_self=True)
        replied = MagicMock()
        replied.author = adapter._client.user
        message = _make_message(author=_make_author(bot=True))
        message.reference = MagicMock(resolved=None, message_id=777)
        message.channel.fetch_message = AsyncMock(return_value=replied)

        self.assertTrue(await adapter._reply_targets_client_user(message))
        message.channel.fetch_message.assert_awaited_once_with(777)


if __name__ == "__main__":
    unittest.main()
