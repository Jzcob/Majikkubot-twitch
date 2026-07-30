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

        # Initialize the extra banned words list
        self.extra_banned_list = []
        # Parse the extra banned words from the environment variable
        extra_banned_words = os.getenv("EXTRA_BANNED_WORDS", "")
        if extra_banned_words:
            self.extra_banned_list = [word.strip() for word in extra_banned_words.split(",") if word.strip()]
        print(f"  - Extra banned words initialized: {self.extra_banned_list}")
        # This will hold the regulars dict from the AdminCog, e.g., {'channel': {'user1', ...}}
        self.regulars_by_channel = {}
        # This will hold channel-specific configs and fetched IDs
        self.channel_data = {}

        # Regex patterns are global and don't need to change
        # Updated to catch Cyrillic homoglyphs and alternative dot characters
        self.LINK_REGEX = re.compile(
            r"(?:https?:\/\/)?(?:[a-zA-Z0-9-]+\s*\.\s*)+[a-zA-Z]{2,9}(?![a-zA-Z0-9])(?:\/\S*)?"
        )
        self.TWITCH_LINK_REGEX = re.compile(r'(\bclips\s*\.\s*)?twitch\s*\.\s*tv\b', re.IGNORECASE)
        
        # Bot's own info, fetched once during setup
        self.moderator_id = None
        self.bot_login_name = None

    async def setup(self, admin_cog_instance: Optional[Any] = None):
        """Performs async setup and receives the regulars dictionary from the AdminCog."""
        # 1. Get the shared regulars list from the AdminCog instance
        if admin_cog_instance and hasattr(admin_cog_instance, 'regulars_by_channel'):
            self.regulars_by_channel = admin_cog_instance.regulars_by_channel
            print("  - MalLinkCog successfully received regulars list from AdminCog.")

        try:
            # 2. Get the bot's own user info
            bot_user_data = [user async for user in self.twitch.get_users()]
            if not bot_user_data:
                raise Exception("Could not get bot's user information.")
            self.moderator_id = bot_user_data[0].id
            self.bot_login_name = bot_user_data[0].login.lower()

            # 3. Get info for all broadcasters in a single API call
            channel_names = [config['name'] for config in self.channel_configs]
            broadcasters_data = {user.login.lower(): user async for user in self.twitch.get_users(logins=channel_names)}

            # 4. Populate self.channel_data with combined config and fetched IDs
            for config in self.channel_configs:
                channel_name = config['name'].lower()
                broadcaster = broadcasters_data.get(channel_name)
                if broadcaster:
                    self.channel_data[channel_name] = {**config, 'broadcaster_id': broadcaster.id}
                    print(f"  - MalLinkCog configured for #{channel_name}")
                else:
                    print(f"  - WARNING: Could not find Twitch user '{channel_name}' in MalLinkCog.")
        except Exception as e:
            print(f"Error during MalLinkCog setup: {e}")
            raise e

    async def send_discord_webhook(self, webhook_url: str, mod_role_id: str, user_name: str, original_message: str):
        """Sends an alert to the correct Discord channel via its webhook."""
        if not webhook_url:
            return
        
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)
            mod_mention = f"<@&{mod_role_id}>" if mod_role_id else "@moderators"
            
            # Updated embed title to reflect that only a deletion occurred
            embed = discord.Embed(title="User Message Deleted for Posting Link", color=discord.Color.red())
            embed.add_field(name="Username", value=user_name, inline=False)
            embed.add_field(name="Original Message", value=f"```{original_message}```", inline=False)
            embed.set_footer(text="Please review user's chat history for a potential ban.")
            
            await webhook.send(content=mod_mention, embed=embed)

    async def on_message(self, msg: ChatMessage):
        """Checks messages for non-Twitch links and takes action."""
        if msg.user.name.lower() == self.bot_login_name:
            return

        channel_name = msg.room.name.lower()
        current_config = self.channel_data.get(channel_name)
        if not current_config:
            return

        # 1. Check if the user is exempt (broadcaster, mod, vip, or regular for THAT channel)
        user_badges = msg.user.badges or {}
        current_regulars = self.regulars_by_channel.get(channel_name, set())
        is_exempt = (
            msg.user.name.lower() == channel_name or
            any(badge in user_badges for badge in ['moderator', 'vip', 'admin']) or
            msg.user.name.lower() in current_regulars
        )
        if is_exempt:
            return

        # 2. Check for a non-Twitch link
        if self.LINK_REGEX.search(msg.text) and not self.TWITCH_LINK_REGEX.search(msg.text):
            print(f"[{channel_name}] Non-Twitch link from {msg.user.name}. Deleting message...")
            try:
                # Silently delete the message via the API
                await self.twitch.delete_chat_message(
                    broadcaster_id=current_config['broadcaster_id'],
                    moderator_id=self.moderator_id,
                    message_id=msg.id
                )
                
                # Send an alert to the correct Discord moderation webhook
                await self.send_discord_webhook(
                    webhook_url=current_config.get('discord_webhook_mod'),
                    mod_role_id=current_config.get('discord_mod_role_id'),
                    user_name=msg.user.name,
                    original_message=msg.text
                )
            except Exception as e:
                print(f"[{channel_name}] Error deleting message from {msg.user.name}: {e}")

# This setup function is called by your main script
async def setup(twitch: Twitch, chat: Chat, channel_configs: List[Dict], admin_cog_instance: Optional[Any] = None):
    """Initializes and registers the cog, passing the AdminCog instance to it."""
    cog = MalLinkCog(twitch, chat, channel_configs)
    await cog.setup(admin_cog_instance)
    chat.register_event(cog.event_name, cog.on_message)
    print("MalLinkCog loaded and message handler registered.")