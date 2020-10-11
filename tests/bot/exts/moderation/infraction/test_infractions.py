import textwrap
import unittest
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from bot.constants import Event
from bot.exts.moderation.infraction.infractions import Infractions
from tests.helpers import MockBot, MockContext, MockGuild, MockMember, MockRole


class TruncationTests(unittest.IsolatedAsyncioTestCase):
    """Tests for ban and kick command reason truncation."""

    def setUp(self):
        self.bot = MockBot()
        self.cog = Infractions(self.bot)
        self.user = MockMember(id=1234, top_role=MockRole(id=3577, position=10))
        self.target = MockMember(id=1265, top_role=MockRole(id=9876, position=0))
        self.guild = MockGuild(id=4567)
        self.ctx = MockContext(bot=self.bot, author=self.user, guild=self.guild)

    @patch("bot.exts.moderation.infraction._utils.get_active_infraction")
    @patch("bot.exts.moderation.infraction._utils.post_infraction")
    async def test_apply_ban_reason_truncation(self, post_infraction_mock, get_active_mock):
        """Should truncate reason for `ctx.guild.ban`."""
        get_active_mock.return_value = None
        post_infraction_mock.return_value = {"foo": "bar"}

        self.cog.apply_infraction = AsyncMock()
        self.bot.get_cog.return_value = AsyncMock()
        self.cog.mod_log.ignore = Mock()
        self.ctx.guild.ban = Mock()

        await self.cog.apply_ban(self.ctx, self.target, "foo bar" * 3000)
        self.ctx.guild.ban.assert_called_once_with(
            self.target,
            reason=textwrap.shorten("foo bar" * 3000, 512, placeholder="..."),
            delete_message_days=0
        )
        self.cog.apply_infraction.assert_awaited_once_with(
            self.ctx, {"foo": "bar"}, self.target, self.ctx.guild.ban.return_value
        )

    @patch("bot.exts.moderation.infraction._utils.post_infraction")
    async def test_apply_kick_reason_truncation(self, post_infraction_mock):
        """Should truncate reason for `Member.kick`."""
        post_infraction_mock.return_value = {"foo": "bar"}

        self.cog.apply_infraction = AsyncMock()
        self.cog.mod_log.ignore = Mock()
        self.target.kick = Mock()

        await self.cog.apply_kick(self.ctx, self.target, "foo bar" * 3000)
        self.target.kick.assert_called_once_with(reason=textwrap.shorten("foo bar" * 3000, 512, placeholder="..."))
        self.cog.apply_infraction.assert_awaited_once_with(
            self.ctx, {"foo": "bar"}, self.target, self.target.kick.return_value
        )


@patch("bot.exts.moderation.infraction.infractions.constants.Roles.voice_verified", new=123456)
class VoiceBanTests(unittest.IsolatedAsyncioTestCase):
    """Tests for voice ban related functions and commands."""

    def setUp(self):
        self.bot = MockBot()
        self.mod = MockMember(top_role=10)
        self.user = MockMember(top_role=1, roles=[MockRole(id=123456)])
        self.ctx = MockContext(bot=self.bot, author=self.mod)
        self.cog = Infractions(self.bot)

    async def test_permanent_voice_ban(self):
        """Should call voice ban applying function without expiry."""
        self.cog.apply_voice_ban = AsyncMock()
        self.assertIsNone(await self.cog.voice_ban(self.cog, self.ctx, self.user, reason="foobar"))
        self.cog.apply_voice_ban.assert_awaited_once_with(self.ctx, self.user, "foobar")

    async def test_temporary_voice_ban(self):
        """Should call voice ban applying function with expiry."""
        self.cog.apply_voice_ban = AsyncMock()
        self.assertIsNone(await self.cog.tempvoiceban(self.cog, self.ctx, self.user, "baz", reason="foobar"))
        self.cog.apply_voice_ban.assert_awaited_once_with(self.ctx, self.user, "foobar", expires_at="baz")

    async def test_voice_unban(self):
        """Should call infraction pardoning function."""
        self.cog.pardon_infraction = AsyncMock()
        self.assertIsNone(await self.cog.unvoiceban(self.cog, self.ctx, self.user))
        self.cog.pardon_infraction.assert_awaited_once_with(self.ctx, "voice_ban", self.user)

    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_not_having_voice_verified_role(self, get_active_infraction_mock):
        """Should send message and not apply infraction when user don't have voice verified role."""
        self.user.roles = [MockRole(id=987)]
        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, "foobar"))
        self.ctx.send.assert_awaited_once()
        get_active_infraction_mock.assert_not_awaited()

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_user_have_active_infraction(self, get_active_infraction, post_infraction_mock):
        """Should return early when user already have Voice Ban infraction."""
        get_active_infraction.return_value = {"foo": "bar"}
        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, "foobar"))
        get_active_infraction.assert_awaited_once_with(self.ctx, self.user, "voice_ban")
        post_infraction_mock.assert_not_awaited()

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_infraction_post_failed(self, get_active_infraction, post_infraction_mock):
        """Should return early when posting infraction fails."""
        self.cog.mod_log.ignore = MagicMock()
        get_active_infraction.return_value = None
        post_infraction_mock.return_value = None
        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, "foobar"))
        post_infraction_mock.assert_awaited_once()
        self.cog.mod_log.ignore.assert_not_called()

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_infraction_post_add_kwargs(self, get_active_infraction, post_infraction_mock):
        """Should pass all kwargs passed to apply_voice_ban to post_infraction."""
        get_active_infraction.return_value = None
        # We don't want that this continue yet
        post_infraction_mock.return_value = None
        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, "foobar", my_kwarg=23))
        post_infraction_mock.assert_awaited_once_with(
            self.ctx, self.user, "voice_ban", "foobar", active=True, my_kwarg=23
        )

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_mod_log_ignore(self, get_active_infraction, post_infraction_mock):
        """Should ignore Voice Verified role removing."""
        self.cog.mod_log.ignore = MagicMock()
        self.cog.apply_infraction = AsyncMock()
        self.user.remove_roles = MagicMock(return_value="my_return_value")

        get_active_infraction.return_value = None
        post_infraction_mock.return_value = {"foo": "bar"}

        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, "foobar"))
        self.cog.mod_log.ignore.assert_called_once_with(Event.member_update, self.user.id)
