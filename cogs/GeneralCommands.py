import os
from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch

class CommandsCog:
    def __init__(self, twitch: Twitch, chat: Chat, target_channel: str):
        self.twitch = twitch
        self.chat = chat
        self.target_channel = target_channel
        self.event_name = ChatEvent.MESSAGE # The event this cog listens to

        # To be populated by the setup method
        self.bot_login_name = None

    async def setup(self):
        """Performs async setup required for the cog."""
        try:
            # Get authenticated bot user info to prevent the bot from replying to itself
            bot_user_gen = self.twitch.get_users()
            bot_user_data = [user async for user in bot_user_gen]
            if not bot_user_data:
                raise Exception("Could not get bot's user information for CommandsCog.")
            self.bot_login_name = bot_user_data[0].login.lower()
            
        except Exception as e:
            print(f"Error during CommandsCog setup: {e}")
            raise e

    async def on_message(self, msg: ChatMessage):
        """This function is called by the Chat instance for each new message."""
        # The bot should not react to its own messages
        if msg.user.name.lower() == self.bot_login_name:
            return

        # --- Command Handling ---
        # Check if the message starts with '!'
        if not msg.text.startswith('!'):
            return

        # Split the message into command and arguments
        parts = msg.text.lower().split()
        command = parts[0]

        # --- Define your commands here ---
        if command == '!hello':
            await self.chat.send_message(self.target_channel, f'Hello, {msg.user.name}!')
        
        if command == '!discord':
            discord_message = "Jzcoob's Discord Server is: https://discord.gg/WGQYdzvn8y"
            # First, send the message to chat
            await self.chat.send_message(self.target_channel, discord_message)
            # Then, pin it as an announcement (only mods can do this)
            if msg.user.is_mod:
                try:
                    await self.twitch.manage_chat_announcements(
                        broadcaster_id=self.broadcaster_id,
                        moderator_id=self.moderator_id,
                        message=discord_message
                    )
                    print(f"Pinned Discord link message.")
                except Exception as e:
                    print(f"Failed to pin message: {e}")
            
        
        # Example of another command
        # if command == '!uptime':
        #     # (Add logic to get stream uptime here)
        #     await self.chat.send_message(self.target_channel, 'The stream has been live for X hours!')


# This setup function is called by main.py to load the cog
async def setup(twitch: Twitch, chat: Chat, target_channel: str):
    """Initializes and registers the cog with the bot."""
    cog = CommandsCog(twitch, chat, target_channel)
    await cog.setup()
    chat.register_event(cog.event_name, cog.on_message)
