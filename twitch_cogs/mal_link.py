import os
import re
import discord
import aiohttp

from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch
from typing import List, Dict, Optional, Any


class MalLinkCog:
    def __init__(self, twitch: Twitch, chat: Chat, channel_configs: List[Dict]):
        self.twitch = twitch
        self.chat = chat
        self.channel_configs = channel_configs
        self.event_name = ChatEvent.MESSAGE

        self.extra_banned_list = []
        extra_banned_words = os.getenv("EXTRA_BANNED_WORDS", "")
        if extra_banned_words:
            self.extra_banned_list = [
                word.strip().lower()
                for word in extra_banned_words.split(",")
                if word.strip()
            ]

        print(f"  - Extra banned words initialized: {self.extra_banned_list}")

        self.regulars_by_channel = {}
        self.channel_data = {}
        self.seen_users = {}
        self.moderator_id = None
        self.bot_login_name = None

        # Normalize common spam obfuscation before regex checks.
        self.DOT_WORD_REGEX = re.compile(r"(?i)(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\})")

        # Twitch links are allowed.
        self.TWITCH_LINK_REGEX = re.compile(
            r"(?i)\b(?:https?://)?(?:www\.)?(?:clips\.)?twitch\s*\.\s*tv\b"
        )

        # Generic domains, including spaces around the dot:
        # twitchstar .com, twitchstar[dot]com, twitchstar (dot) com, etc.
        self.DOMAIN_REGEX = re.compile(
            r"""(?ix)
            \b
            (?:https?://\s*)?
            (?:www\s*\.\s*)?
            [a-z0-9][a-z0-9_-]{1,62}
            (?:\s*\.\s*|\s+(?:dot)\s+)
            (?:com|net|org|tv|xyz|io|site|online|ru|cc|gg|live|shop|info|biz)
            \b
            """
        )

        # Known engagement/viewbot wording. Allows unusual spacing/casing.
        self.BOT_PHRASE_REGEX = re.compile(
            r"""(?ix)
            \b(?:
                ai\s*viewers?
                |(?:buy|get)\s+(?:cheap\s+)?(?:views?|viewers?|followers?|primes?|chatters?|subs?|subscribers?)
                |cheap\s+(?:views?|viewers?|followers?|subs?|subscribers?)
                |(?:free|real|active)\s+(?:views?|viewers?|followers?)
                |(?:boost|grow|promote)\s+(?:your\s+)?(?:stream|channel|viewers?|followers?)
                |streamboo
                |bigfollows
                |viewerlabs
                |twitchstar
            )\b
            """
        )

        # Known spam-style intros/pitches.
        self.SPAM_PITCH_REGEX = re.compile(
            r"""(?ix)
            (?:
                yo\s+bro.*?(?:top\s+twitch\s+streamer|discord|peter\s+sent\s+u)
                |
                \b(?:ai\s*viewers?|twitchstar|streamboo|bigfollows|viewerlabs)\b
            )
            """
        )

        # First-time chatters get a stricter check.
        self.HARSH_FIRST_MSG_REGEX = re.compile(
            r"""(?ix)
            \b(?:https?://|www\.)\S+
            |
            \b[a-z0-9][a-z0-9_-]{1,62}\s*\.\s*
            (?:com|net|org|tv|xyz|io|site|online|ru|cc|gg|live|shop|info|biz)\b
            |
            \b(?:viewers?|followers?|primes?|subscribers?|chatters?|bot(?:s|ting)?|promote\s+your|ai\s*viewers?)\b
            """
        )

    @staticmethod
    def _normalize_message(text: str) -> str:
        text = text or ""
        text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
        text = re.sub(r"(?i)(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\})", ".", text)
        text = re.sub(r"\s*\.\s*", ".", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    async def setup(self, admin_cog_instance: Optional[Any] = None):
        if admin_cog_instance and hasattr(admin_cog_instance, "regulars_by_channel"):
            self.regulars_by_channel = admin_cog_instance.regulars_by_channel
            print("  - MalLinkCog successfully received regulars list from AdminCog.")

        try:
            bot_user_data = [user async for user in self.twitch.get_users()]
            if not bot_user_data:
                raise Exception("Could not get bot's user information.")

            self.moderator_id = bot_user_data[0].id
            self.bot_login_name = bot_user_data[0].login.lower()

            channel_names = [
                config.get("name", "").strip()
                for config in self.channel_configs
                if config.get("name")
            ]

            broadcasters_data = {
                user.login.lower(): user
                async for user in self.twitch.get_users(logins=channel_names)
            }

            for config in self.channel_configs:
                if not config.get("name"):
                    continue

                channel_name = config["name"].lower()
                broadcaster = broadcasters_data.get(channel_name)

                if broadcaster:
                    self.channel_data[channel_name] = {
                        **config,
                        "broadcaster_id": broadcaster.id
                    }
                    print(f"  - MalLinkCog configured for #{channel_name}")
                else:
                    print(f"  - WARNING: Could not find Twitch user '{channel_name}' in MalLinkCog.")

        except Exception as e:
            print(f"Error during MalLinkCog setup: {e}")
            raise

    async def send_discord_webhook(
        self,
        webhook_url: Optional[str],
        mod_role_id: Optional[str],
        user_name: str,
        original_message: str,
        reason: str,
    ):
        # Discord logging is completely optional.
        if not webhook_url:
            return

        try:
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(webhook_url, session=session)
                mod_mention = f"<@&{mod_role_id}>" if mod_role_id else None

                embed = discord.Embed(
                    title="Twitch Spam Removed",
                    color=discord.Color.red()
                )
                embed.add_field(name="Username", value=user_name, inline=False)
                embed.add_field(name="Action", value="Message deleted", inline=False)
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(
                    name="Original Message",
                    value=f"```{original_message[:1000]}```",
                    inline=False,
                )

                await webhook.send(content=mod_mention, embed=embed)

        except Exception as e:
            print(f"Discord moderation log skipped/failed: {e}")

    async def remove_spam_message(
        self,
        msg: ChatMessage,
        current_config: Dict,
        reason: str,
    ):
        """Delete the triggering spam message. Do not timeout or ban the user."""
        channel_name = msg.room.name.lower()
        broadcaster_id = str(current_config["broadcaster_id"])
        moderator_id = str(self.moderator_id)

        delete_ok = False

        try:
            await self.twitch.delete_chat_message(
                broadcaster_id=broadcaster_id,
                moderator_id=moderator_id,
                message_id=msg.id,
            )
            delete_ok = True
            print(f"[{channel_name}] Deleted spam message from {msg.user.name} ({reason}).")
        except Exception as e:
            print(
                f"[{channel_name}] ERROR deleting message from "
                f"{msg.user.name}: {type(e).__name__}: {e}"
            )

        await self.send_discord_webhook(
            webhook_url=current_config.get("discord_webhook_mod"),
            mod_role_id=current_config.get("discord_mod_role_id"),
            user_name=msg.user.name,
            original_message=msg.text,
            reason=reason,
        )

        print(f"[{channel_name}] Spam action result for {msg.user.name}: delete={delete_ok}")

    def detect_spam(self, text: str, first_message: bool):
        normalized = self._normalize_message(text)

        # Twitch URLs remain whitelisted.
        if self.TWITCH_LINK_REGEX.search(normalized):
            # A Twitch URL can still be spam if it also contains an obvious
            # engagement-selling phrase.
            if not self.BOT_PHRASE_REGEX.search(normalized):
                return None

        if self.BOT_PHRASE_REGEX.search(normalized):
            return "Viewbot / engagement spam"

        if self.SPAM_PITCH_REGEX.search(normalized):
            return "Known spam pitch"

        if self.DOMAIN_REGEX.search(normalized):
            return "Non-Twitch link"

        if first_message and self.HARSH_FIRST_MSG_REGEX.search(normalized):
            return "Suspicious first message"

        lowered = normalized.lower()
        for banned in self.extra_banned_list:
            if banned and banned in lowered:
                return f"Configured banned phrase: {banned}"

        return None

    async def on_message(self, msg: ChatMessage):
        if self.bot_login_name and msg.user.name.lower() == self.bot_login_name:
            return

        channel_name = msg.room.name.lower()
        current_config = self.channel_data.get(channel_name)
        if not current_config:
            return

        if channel_name not in self.seen_users:
            self.seen_users[channel_name] = set()

        user_lower = msg.user.name.lower()
        user_badges = msg.user.badges or {}
        current_regulars = self.regulars_by_channel.get(channel_name, set())

        is_exempt = (
            user_lower == channel_name
            or any(badge in user_badges for badge in ["moderator", "vip", "admin"])
            or user_lower in current_regulars
        )
        if is_exempt:
            return

        first_message = user_lower not in self.seen_users[channel_name]
        reason = self.detect_spam(msg.text, first_message)

        if reason:
            print(
                f"[{channel_name}] {reason} detected from {msg.user.name}: "
                f"{msg.text!r}"
            )
            await self.remove_spam_message(msg, current_config, reason)
            return

        # Only mark the user as seen after a safe first message.
        self.seen_users[channel_name].add(user_lower)


async def setup(
    twitch: Twitch,
    chat: Chat,
    channel_configs: List[Dict],
    admin_cog_instance: Optional[Any] = None,
):
    cog = MalLinkCog(twitch, chat, channel_configs)
    await cog.setup(admin_cog_instance)
    chat.register_event(cog.event_name, cog.on_message)
    print("MalLinkCog loaded and message handler registered.")
    return cog