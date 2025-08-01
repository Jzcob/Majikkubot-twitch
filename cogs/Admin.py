import json
from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch

class AdminCog:
    def __init__(self, twitch: Twitch, chat: Chat, target_channel: str, regulars_file: str = 'regulars.json'):
        self.twitch = twitch
        self.chat = chat
        self.target_channel = target_channel
        self.event_name = ChatEvent.MESSAGE
        self.regulars_file = regulars_file
        self.regulars = self.load_regulars()

        # To be populated by the setup method
        self.bot_login_name = None

    def load_regulars(self) -> set:
        """Loads the list of regular users from a JSON file."""
        try:
            with open(self.regulars_file, 'r') as f:
                data = json.load(f)
                # Ensure data is a list of lowercase strings
                return set(str(name).lower() for name in data)
        except (FileNotFoundError, json.JSONDecodeError):
            # If the file doesn't exist or is empty/corrupt, start with an empty set
            return set()

    def save_regulars(self):
        """Saves the current list of regular users to the JSON file."""
        with open(self.regulars_file, 'w') as f:
            # Convert the set to a list for JSON serialization
            json.dump(list(self.regulars), f, indent=4)

    async def setup(self):
        """Performs async setup required for the cog."""
        try:
            bot_user_gen = self.twitch.get_users()
            bot_user_data = [user async for user in bot_user_gen]
            if not bot_user_data:
                raise Exception("Could not get bot's user information for AdminCog.")
            self.bot_login_name = bot_user_data[0].login.lower()
        except Exception as e:
            print(f"Error during AdminCog setup: {e}")
            raise e

    async def on_message(self, msg: ChatMessage):
        """Handles chat commands for managing regulars."""
        if msg.user.name.lower() == self.bot_login_name:
            return

        if not msg.text.startswith('!'):
            return

        # Only moderators can use these commands
        user_badges = msg.user.badges or {}
        if 'moderator' not in user_badges and msg.user.name.lower() != self.target_channel.lower():
            return

        parts = msg.text.lower().split()
        command = parts[0]
        
        if command == '!addregular':
            if len(parts) < 2:
                await self.chat.send_message(self.target_channel, "Usage: !addregular <username>")
                return
            
            username_to_add = parts[1].lstrip('@')
            if username_to_add in self.regulars:
                await self.chat.send_message(self.target_channel, f"{username_to_add} is already a regular.")
            else:
                self.regulars.add(username_to_add)
                self.save_regulars()
                await self.chat.send_message(self.target_channel, f"{username_to_add} has been added to the regulars list.")

        elif command == '!removeregular':
            if len(parts) < 2:
                await self.chat.send_message(self.target_channel, "Usage: !removeregular <username>")
                return

            username_to_remove = parts[1].lstrip('@')
            if username_to_remove in self.regulars:
                self.regulars.remove(username_to_remove)
                self.save_regulars()
                await self.chat.send_message(self.target_channel, f"{username_to_remove} has been removed from the regulars list.")
            else:
                await self.chat.send_message(self.target_channel, f"{username_to_remove} is not in the regulars list.")

# This setup function is called by main.py to load the cog
async def setup(twitch: Twitch, chat: Chat, target_channel: str):
    """Initializes and registers the cog with the bot."""
    cog = AdminCog(twitch, chat, target_channel)
    await cog.setup()
    # We need to register the on_message handler for this cog as well
    chat.register_event(cog.event_name, cog.on_message)
    # Return the cog instance so other cogs can access its data
    return cog
