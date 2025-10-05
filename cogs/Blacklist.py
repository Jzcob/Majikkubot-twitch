import re
import discord
import aiohttp
from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch
from typing import List, Dict

class BlacklistCog:
    def __init__(self, twitch: Twitch, chat: Chat, channel_configs: List[Dict]):
        self.twitch = twitch
        self.chat = chat
        self.channel_configs = channel_configs  # Store configs to use in setup
        # This dictionary will be populated in setup() with all channel-specific data
        self.channel_data = {}
        self.event_name = ChatEvent.MESSAGE

        # Regex is the same for all channels, so it stays here
        self.BLACKLIST_REGEX = re.compile(
            r'\b(f[a@4]g{1,2}(s|ot)?|n[i!1]g{2,}[e3a@4]r(s|z)?|c[u*]nt|wh[o0]re|tr[a@]nny|r[e3]t[a@]rd|kys|kill\s*your\s*self)\b',
            re.IGNORECASE
        )
        
        # Bot's own info, fetched once during setup
        self.moderator_id = None
        self.bot_login_name = None

    async def setup(self):
        """Performs async setup for the cog, fetching all required user IDs."""
        try:
            # 1. Get the bot's own user info (moderator_id) once
            bot_user_data = [user async for user in self.twitch.get_users()]
            if not bot_user_data:
                raise Exception("Could not get bot's user information.")
            self.moderator_id = bot_user_data[0].id
            self.bot_login_name = bot_user_data[0].login.lower()

            # 2. Get info for all broadcasters in a single API call for efficiency
            channel_names = [config['name'] for config in self.channel_configs]
            users_gen = self.twitch.get_users(logins=channel_names)
            broadcasters_data = {user.login.lower(): user async for user in users_gen}

            # 3. Populate self.channel_data with combined config and fetched IDs
            for config in self.channel_configs:
                channel_name = config['name'].lower()
                broadcaster = broadcasters_data.get(channel_name)
                if broadcaster:
                    # Merge the original config with the fetched broadcaster ID
                    self.channel_data[channel_name] = {
                        **config,  # Unpack all original key-values from config.json
                        'broadcaster_id': broadcaster.id
                    }
                    print(f"  - BlacklistCog configured for #{channel_name}")
                else:
                    print(f"  - WARNING: Could not find Twitch user for channel '{channel_name}'")
        except Exception as e:
            print(f"Error during BlacklistCog setup: {e}")
            raise e

    async def send_audit_log(self, webhook_url: str, user_name: str, original_message: str):
        """Sends a blacklist log to the correct Discord channel via its webhook."""
        if not webhook_url:
            return  # Silently fail if webhook URL is missing for this channel
        
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)
            embed = discord.Embed(
                title="Audit Log: Blacklisted Word Detected",
                description="The user's message was automatically deleted.",
                color=discord.Color.from_rgb(255, 127, 80) # Coral
            )
            embed.add_field(name="Username", value=user_name, inline=False)
            embed.add_field(name="Original Message", value=f"```{original_message}```", inline=False)
            await webhook.send(embed=embed)

    async def on_message(self, msg: ChatMessage):
        """This function is called for each new message in any channel."""
        # Ignore the bot's own messages
        if msg.user.name.lower() == self.bot_login_name:
            return

        # Get the channel where the message was sent
        channel_name = msg.room.name.lower()
        current_config = self.channel_data.get(channel_name)
        
        # If the message is in a channel the cog isn't configured for, do nothing
        if not current_config:
            return

        # 1. Check for permissions (broadcaster, mod, vip, etc. are exempt)
        user_badges = msg.user.badges or {}
        is_exempt = (
            msg.user.name.lower() == channel_name or
            any(badge in user_badges for badge in ['moderator', 'vip', 'admin'])
        )
        if is_exempt:
            return

        # 2. Check if the message contains a blacklisted word
        if self.BLACKLIST_REGEX.search(msg.text):
            print(f"[{channel_name}] Blacklisted word from {msg.user.name}. Taking action...")
            try:
                # Delete the message in the correct channel
                await self.chat.send_message(channel_name, f'/delete {msg.id}')

                # Send an alert to that channel's specific Discord log webhook
                log_webhook_url = current_config.get('discord_webhook_log')
                await self.send_audit_log(log_webhook_url, msg.user.name, msg.text)
            except Exception as e:
                print(f"Error taking action for blacklist violation in #{channel_name}: {e}")

# This setup function is called by your main script
async def setup(twitch: Twitch, chat: Chat, channel_configs: List[Dict]):
    """Initializes and registers the cog with the bot."""
    cog = BlacklistCog(twitch, chat, channel_configs)
    await cog.setup()
    chat.register_event(cog.event_name, cog.on_message)
    print("BlacklistCog loaded and message handler registered.")