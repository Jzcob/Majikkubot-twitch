from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch
from typing import List, Dict

class CommandsCog:
    def __init__(self, twitch: Twitch, chat: Chat, channel_configs: List[Dict]):
        self.twitch = twitch
        self.chat = chat
        self.channel_configs = channel_configs
        self.event_name = ChatEvent.MESSAGE
        
        # This dictionary will hold all channel-specific data, including fetched IDs
        self.channel_data = {}
        
        # Bot's own info, will be fetched once in setup
        self.bot_login_name = None
        self.moderator_id = None

    async def setup(self):
        """Performs async setup for the cog, fetching all required user IDs."""
        try:
            # 1. Get the bot's own user info (for moderator_id and to ignore its own messages)
            bot_user_data = [user async for user in self.twitch.get_users()]
            if not bot_user_data:
                raise Exception("Could not get bot's user information for CommandsCog.")
            self.moderator_id = bot_user_data[0].id
            self.bot_login_name = bot_user_data[0].login.lower()

            # 2. Get info for all broadcasters in a single API call
            channel_names = [config['name'] for config in self.channel_configs]
            users_gen = self.twitch.get_users(logins=channel_names)
            broadcasters_data = {user.login.lower(): user async for user in users_gen}

            # 3. Populate self.channel_data with combined config and fetched IDs
            for config in self.channel_configs:
                channel_name = config['name'].lower()
                broadcaster = broadcasters_data.get(channel_name)
                if broadcaster:
                    # Merge the original config with the fetched broadcaster ID
                    self.channel_data[channel_name] = {**config, 'broadcaster_id': broadcaster.id}
                    print(f"  - CommandsCog configured for #{channel_name}")
                else:
                    print(f"  - WARNING: Could not find Twitch user for channel '{channel_name}' in CommandsCog.")
        except Exception as e:
            print(f"Error during CommandsCog setup: {e}")
            raise e

    async def on_message(self, msg: ChatMessage):
        """Handles commands for all connected channels."""
        if msg.user.name.lower() == self.bot_login_name:
            return

        if not msg.text.startswith('!'):
            return

        # Get the channel where the message was sent and find its config
        channel_name = msg.room.name.lower()
        current_config = self.channel_data.get(channel_name)

        if not current_config:
            return # Don't respond in a channel that isn't fully configured

        parts = msg.text.lower().split()
        command = parts[0]

        # --- Define your commands here ---
        if command == '!hello':
            await self.chat.send_message(channel_name, f'Hello, {msg.user.name}! 👋')
        
        elif command == '!discord':
            discord_link = current_config.get('discord_invite_link')
            if not discord_link:
                return # Don't do anything if the link isn't in config.json
            
            discord_message = f"Join the community on Discord! {discord_link}"
            await self.chat.send_message(channel_name, discord_message)
            
            # Moderator-only: Pin the message as an announcement
            user_badges = msg.user.badges or {}
            if 'moderator' in user_badges or msg.user.name.lower() == channel_name:
                try:
                    await self.twitch.manage_chat_announcements(
                        broadcaster_id=current_config['broadcaster_id'],
                        moderator_id=self.moderator_id,
                        message=discord_message
                    )
                    print(f"[{channel_name}] Pinned Discord link message.")
                except Exception as e:
                    print(f"[{channel_name}] Failed to pin message: {e}")
        
        elif command == '!lurk':
            lurk_message = f"{msg.user.name} is now lurking! 👀 Thanks for the support!"
            await self.chat.send_message(channel_name, lurk_message)

        elif command == '!youtube':
            youtube_link = current_config.get('youtube_channel_link')
            if youtube_link:
                youtube_message = f"Check out the YouTube channel! {youtube_link}"
                await self.chat.send_message(channel_name, youtube_message)
        

# This setup function is called by your main script
async def setup(twitch: Twitch, chat: Chat, channel_configs: List[Dict]):
    """Initializes and registers the cog with the bot."""
    cog = CommandsCog(twitch, chat, channel_configs)
    await cog.setup()
    chat.register_event(cog.event_name, cog.on_message)
    print("CommandsCog loaded and message handler registered.")