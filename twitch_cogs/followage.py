import os
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch
from typing import List, Dict

class FollowageCog:
    def __init__(self, twitch: Twitch, chat: Chat, channel_configs: List[Dict]):
        self.twitch = twitch
        self.chat = chat
        self.channel_configs = channel_configs
        self.event_name = ChatEvent.MESSAGE
        self.bot_login_name = None

    async def setup(self):
        """Performs async setup to fetch the bot's own user ID."""
        try:
            bot_user_data = [user async for user in self.twitch.get_users()]
            if bot_user_data:
                self.bot_login_name = bot_user_data[0].login.lower()
        except Exception as e:
            print(f"Error during FollowageCog setup: {e}")

    async def on_message(self, msg: ChatMessage):
        """Handles the !followage command."""
        if msg.user.name.lower() == self.bot_login_name or not msg.text.startswith('!'):
            return

        parts = msg.text.lower().split()
        command = parts[0]

        if command == '!followage':
            channel_name = msg.room.name.lower()
            user_id = msg.user.id
            user_name = msg.user.name

            try:
                # 1. Fetch the broadcaster's Twitch ID dynamically
                broadcasters = [u async for u in self.twitch.get_users(logins=[channel_name])]
                if not broadcasters:
                    return
                broadcaster_id = broadcasters[0].id

                # 2. Query the follower endpoint
                followers = [f async for f in self.twitch.get_channel_followers(broadcaster_id=broadcaster_id, user_id=user_id)]
                
                # If the list is empty, they are not following
                if not followers:
                    await self.chat.send_message(channel_name, f"@{user_name}, you are not currently following this channel!")
                    return

                # 3. Calculate the time difference safely
                followed_at = followers[0].followed_at
                now = datetime.now(timezone.utc)
                
                # Ensure followed_at is timezone-aware (Twitch API usually provides UTC awareness, 
                # but this protects against naive datetimes if any environment quirks exist)
                if followed_at.tzinfo is None:
                    followed_at = followed_at.replace(tzinfo=timezone.utc)

                diff = relativedelta(now, followed_at)

                # Format the output cleanly
                time_parts = []
                if diff.years > 0: 
                    time_parts.append(f"{diff.years} year{'s' if diff.years > 1 else ''}")
                if diff.months > 0: 
                    time_parts.append(f"{diff.months} month{'s' if diff.months > 1 else ''}")
                if diff.days > 0: 
                    time_parts.append(f"{diff.days} day{'s' if diff.days > 1 else ''}")

                if not time_parts:
                    time_string = "less than a day"
                else:
                    time_string = ", ".join(time_parts)

                await self.chat.send_message(channel_name, f"@{user_name} has been following for {time_string}!")

            except Exception as e:
                print(f"Followage API error: {e}")
                await self.chat.send_message(channel_name, f"@{user_name}, I ran into an error checking your follow date.")

async def setup(twitch: Twitch, chat: Chat, channel_configs: List[Dict], **kwargs):
    cog = FollowageCog(twitch, chat, channel_configs)
    await cog.setup()
    chat.register_event(cog.event_name, cog.on_message)
    print("  - FollowageCog fully initialized.")
    return cog