import re
import os
import discord
import aiohttp
from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch

class BlacklistCog:
    def __init__(self, twitch: Twitch, chat: Chat, target_channel: str):
        self.twitch = twitch
        self.chat = chat
        self.target_channel = target_channel
        self.event_name = ChatEvent.MESSAGE # The event this cog listens to

        # --- Cog-specific Configuration ---
        # Use a separate webhook URL specifically for logging blacklist events
        self.DISCORD_WEBHOOK_LOG_LOG = os.environ.get('DISCORD_WEBHOOK_LOG')

        # The regex from the "Regex for Blacklisted Words" document
        self.BLACKLIST_REGEX = re.compile(
            r'\b(f[a@4]g{1,2}(s|ot)?|n[i!1]g{2,}[e3a@4]r(s|z)?|c[u*]nt|wh[o0]re|tr[a@]nny|r[e3]t[a@]rd|kys|kill\s*your\s*self)\b',
            re.IGNORECASE
        )
        
        # To be populated by the setup method
        self.broadcaster_id = None
        self.moderator_id = None
        self.bot_login_name = None

    async def setup(self):
        """Performs async setup required for the cog, like fetching user IDs."""
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
            print(f"Error during BlacklistCog setup: {e}")
            raise e

    async def send_audit_log(self, user_name: str, original_message: str):
        """Sends a blacklist log to a dedicated Discord channel via webhook."""
        if not self.DISCORD_WEBHOOK_LOG:
            # Silently fail if the log URL isn't configured
            return
        
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(self.DISCORD_WEBHOOK_LOG, session=session)
            
            embed = discord.Embed(
                title="Audit Log: Blacklisted Word Detected",
                description="The user's message was automatically deleted.",
                color=discord.Color.from_rgb(255, 127, 80) # Coral color
            )
            embed.add_field(name="Username", value=user_name, inline=False)
            embed.add_field(name="Original Message", value=f"```{original_message}```", inline=False)
            
            # Send the embed without any content/mention
            await webhook.send(embed=embed)

    async def on_message(self, msg: ChatMessage):
        """This function is called by the Chat instance for each new message."""
        # The bot should not react to its own messages
        if msg.user.name.lower() == self.bot_login_name:
            return

        # 1. Check for permissions. If user is exempt, do nothing.
        user_badges = msg.user.badges or {}
        if msg.user.name.lower() == self.target_channel.lower() or 'moderator' in user_badges or 'vip' in user_badges or 'admin' in user_badges:
            return

        # 2. Check if the message contains a blacklisted word
        if self.BLACKLIST_REGEX.search(msg.text):
            print(f"Blacklisted word detected from {msg.user.name}. Taking action...")
            try:
                # Delete the offending message
                await self.chat.send_message(self.target_channel, f'/delete {msg.id}')

                # Send an alert to the Discord audit channel
                await self.send_audit_log(msg.user.name, msg.text)

            except Exception as e:
                print(f"Error taking action for blacklist violation against {msg.user.name}: {e}")

# This setup function is called by main.py to load the cog
async def setup(twitch: Twitch, chat: Chat, target_channel: str):
    """Initializes and registers the cog with the bot."""
    cog = BlacklistCog(twitch, chat, target_channel)
    await cog.setup()
    chat.register_event(cog.event_name, cog.on_message)
