import json
import re
from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch

class AdminCog:
    def __init__(self, twitch: Twitch, chat: Chat, channel_configs: list):
        self.twitch = twitch
        self.chat = chat
        # This dictionary will hold the set of regulars for each channel
        self.regulars_by_channel = {}
        self.event_name = ChatEvent.MESSAGE
        self.bot_login_name = None

        # Regex to ensure we don't auto-promote someone sending a link
        self.LINK_REGEX = re.compile(
            r"(?:https?:\/\/)?(?:[a-zA-Z0-9-]+\s*\.\s*)+[a-zA-Z]{2,9}(?![a-zA-Z0-9])(?:\/\S*)?"
        )

        # Load regulars for each configured channel
        for config in channel_configs:
            channel_name = config['name']
            self.regulars_by_channel[channel_name] = self.load_regulars(channel_name)
            print(f"  - Loaded {len(self.regulars_by_channel[channel_name])} regulars for #{channel_name}")

    def get_regulars_filename(self, channel_name: str) -> str:
        """Generates a unique filename for each channel's regulars list."""
        return f"{channel_name}_regulars.json"

    def load_regulars(self, channel_name: str) -> set:
        """Loads the list of regular users from a channel-specific JSON file."""
        filename = self.get_regulars_filename(channel_name)
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                return set(str(name).lower() for name in data)
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

    def save_regulars(self, channel_name: str):
        """Saves the current list of regular users for a specific channel."""
        filename = self.get_regulars_filename(channel_name)
        regulars_set = self.regulars_by_channel.get(channel_name, set())
        with open(filename, 'w') as f:
            json.dump(list(regulars_set), f, indent=4)

    async def setup(self):
        """Performs async setup to get the bot's own username."""
        try:
            bot_user_data = [user async for user in self.twitch.get_users()]
            if not bot_user_data:
                raise Exception("Could not get bot's user information for AdminCog.")
            self.bot_login_name = bot_user_data[0].login.lower()
        except Exception as e:
            print(f"Error during AdminCog setup: {e}")
            raise e

    async def on_message(self, msg: ChatMessage):
        """Handles chat commands and Auto-Regular logic."""
        # Ignore messages from the bot itself
        if msg.user.name.lower() == self.bot_login_name:
            return

        channel_name = msg.room.name.lower()
        current_regulars_list = self.regulars_by_channel.get(channel_name)
        
        # Guard clause: Ensure we have data for this channel
        if current_regulars_list is None:
            return

        username = msg.user.name.lower()

        # --- 1. COMMAND HANDLER ---
        if msg.text.startswith('!'):
            user_badges = msg.user.badges or {}
            is_mod = 'moderator' in user_badges
            is_broadcaster = username == channel_name
            
            # Only process manual commands if user is Mod or Broadcaster
            if is_mod or is_broadcaster:
                parts = msg.text.lower().split()
                command = parts[0]

                if command == '!addregular':
                    if len(parts) < 2:
                        await self.chat.send_message(channel_name, "Usage: !addregular <username>")
                        return
                    
                    username_to_add = parts[1].lstrip('@')
                    if username_to_add in current_regulars_list:
                        await self.chat.send_message(channel_name, f"{username_to_add} is already a regular.")
                    else:
                        current_regulars_list.add(username_to_add)
                        self.save_regulars(channel_name)
                        await self.chat.send_message(channel_name, f"{username_to_add} has been added to the regulars list.")
                    return # Exit after handling command

                elif command == '!removeregular':
                    if len(parts) < 2:
                        await self.chat.send_message(channel_name, "Usage: !removeregular <username>")
                        return

                    username_to_remove = parts[1].lstrip('@')
                    if username_to_remove in current_regulars_list:
                        current_regulars_list.remove(username_to_remove)
                        self.save_regulars(channel_name)
                        await self.chat.send_message(channel_name, f"{username_to_remove} has been removed from the regulars list.")
                    else:
                        await self.chat.send_message(channel_name, f"{username_to_remove} is not in the regulars list.")
                    return # Exit after handling command

        # --- 2. AUTO-ADD REGULAR LOGIC ---
        # If the user is NOT a regular, check if we should add them
        if username not in current_regulars_list:
            
            # CRITICAL: Do not auto-add if the message contains a link.
            # We want MalLinkCog to ban them, not AdminCog to whitelist them.
            if self.LINK_REGEX.search(msg.text):
                # We do nothing here. MalLinkCog will see the link, 
                # see they aren't regular, and time them out.
                return

            # If no link, they are a "normal user". Add them to the list.
            current_regulars_list.add(username)
            self.save_regulars(channel_name)
            print(f"[{channel_name}] Auto-added {username} to regulars list.")


# This setup function is called by your main script to load the cog
async def setup(twitch: Twitch, chat: Chat, channel_configs: list):
    """Initializes and registers the cog with the bot for multiple channels."""
    cog = AdminCog(twitch, chat, channel_configs)
    await cog.setup()
    chat.register_event(cog.event_name, cog.on_message)
    print("AdminCog loaded and message handler registered.")
    return cog