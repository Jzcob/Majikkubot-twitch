import re
import os
import discord
import aiohttp
from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch

class MalLinkCog:
    def __init__(self, twitch: Twitch, chat: Chat, target_channel: str):
        self.twitch = twitch
        self.chat = chat
        self.target_channel = target_channel
        self.event_name = ChatEvent.MESSAGE # The event this cog listens to
        self.regulars = set() # This will be populated by the setup function

        # --- Cog-specific Configuration ---
        self.DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_MOD') # Using your updated variable name
        self.DISCORD_MOD_ROLE_ID = os.environ.get('DISCORD_MOD_ROLE_ID')
        
        # Regex to find any potential link with spaces around the dot
        self.LINK_REGEX = re.compile(
            r"(?:https?:\/\/)?(?:[a-zA-Z0-9-]+\s*\.\s*)+[a-zA-Z]{2,9}(?![a-zA-Z0-9])(?:\/\S*)?"
        )
        
        # Regex to specifically find twitch.tv or clips.twitch.tv links, even with spaces
        self.TWITCH_LINK_REGEX = re.compile(r'(\bclips\s*\.\s*)?twitch\s*\.\s*tv\b', re.IGNORECASE)
        
        # To be populated by the setup method
        self.broadcaster_id = None
        self.moderator_id = None
        self.bot_login_name = None

    async def setup(self, admin_cog_instance=None):
        """Performs async setup and receives the regulars list from the admin cog."""
        if admin_cog_instance:
            self.regulars = admin_cog_instance.regulars

        try:
            # Get broadcaster info
            users_gen = self.twitch.get_users(logins=[self.target_channel])
            broadcaster_data = [user async for user in users_gen]
            if not broadcaster_data:
                raise Exception(f"Could not find user for channel '{self.target_channel}'")
            self.broadcaster_id = broadcaster_data[0].id

            # Get authenticated bot user info
            bot_user_gen = self.twitch.get_users()
            bot_user_data = [user async for user in bot_user_gen]
            if not bot_user_data:
                raise Exception("Could not get bot's user information.")
            bot_user_info = bot_user_data[0]
            self.moderator_id = bot_user_info.id
            self.bot_login_name = bot_user_info.login.lower()
            
        except Exception as e:
            print(f"Error during MalLinkCog setup: {e}")
            raise e

    async def send_discord_webhook(self, user_name: str, original_message: str):
        """Sends a timeout alert to a Discord channel via webhook."""
        if not self.DISCORD_WEBHOOK_URL:
            print("Warning: DISCORD_WEBHOOK_MOD is not set. Cannot send alert.")
            return
        
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(self.DISCORD_WEBHOOK_URL, session=session)
            mod_mention = f"<@&{self.DISCORD_MOD_ROLE_ID}>" if self.DISCORD_MOD_ROLE_ID else "@moderators"
            
            embed = discord.Embed(title="User Timed Out for Posting Link", color=discord.Color.red())
            embed.add_field(name="Username", value=user_name, inline=False)
            embed.add_field(name="Original Message", value=f"```{original_message}```", inline=False)
            embed.set_footer(text="Please review user's chat history for a potential ban.")
            
            await webhook.send(content=mod_mention, embed=embed)

    async def on_message(self, msg: ChatMessage):
        """This function is called by the Chat instance for each new message."""
        if msg.user.name.lower() == self.bot_login_name:
            return

        user_badges = msg.user.badges or {}
        if msg.user.name.lower() == self.target_channel.lower() or 'moderator' in user_badges or 'vip' in user_badges or 'admin' in user_badges or msg.user.name.lower() in self.regulars:
            return

        if self.LINK_REGEX.search(msg.text) and not self.TWITCH_LINK_REGEX.search(msg.text):
            print(f"Non-Twitch link detected from {msg.user.name}. Taking action...")
            try:
                await self.chat.send_message(self.target_channel, f'/delete {msg.id}')
                await self.twitch.ban_user(
                    broadcaster_id=self.broadcaster_id,
                    moderator_id=self.moderator_id,
                    user_id=msg.user.id,
                    duration=600,
                    reason="Posting non-Twitch links."
                )
                await self.send_discord_webhook(msg.user.name, msg.text)
            except Exception as e:
                print(f"Error taking action against {msg.user.name}: {e}")

# This setup function is called by main.py to load the cog
async def setup(twitch: Twitch, chat: Chat, target_channel: str, admin_cog_instance=None):
    """Initializes and registers the cog with the bot."""
    cog = MalLinkCog(twitch, chat, target_channel)
    await cog.setup(admin_cog_instance)
    chat.register_event(cog.event_name, cog.on_message)
