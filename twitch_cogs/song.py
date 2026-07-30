import aiohttp
import os
from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch
from typing import List, Dict

# Set your Last.fm API key here or in your environment variables
LASTFM_API_KEY = os.getenv('LASTFM_API_KEY')

class Song:
    def __init__(self, twitch: Twitch, chat: Chat, channel_configs: List[Dict]):
        self.twitch = twitch
        self.chat = chat
        self.channel_configs = channel_configs
        self.event_name = ChatEvent.MESSAGE
        
        # Create a dictionary for quick lookup by channel name
        self.channel_data = {config['name'].lower(): config for config in channel_configs}
        
        # Bot's own info
        self.bot_login_name = None

    async def get_current_song(self, lastfm_username: str) -> str:
        """Asynchronously fetches the currently playing song from Last.fm API."""
        url = f"http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={lastfm_username}&api_key={LASTFM_API_KEY}&format=json&limit=1"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        try:
                            track_data = data['recenttracks']['track']
                            
                            # Last.fm returns a dict if there's only 1 track, or a list if > 1
                            if isinstance(track_data, list):
                                if not track_data: # If the list is completely empty
                                    return "Nothing is currently playing."
                                track = track_data[0]
                            elif isinstance(track_data, dict):
                                track = track_data
                            else:
                                return "Could not parse the song data."

                            # The '@attr' tag only exists if the song is actively playing right now.
                            if '@attr' in track and track['@attr'].get('nowplaying') == 'true':
                                artist = track['artist']['#text']
                                song = track['name']
                                return f"🎵 Now playing: {song} - {artist}"
                            else:
                                return "Nothing is currently playing."
                        except (KeyError, IndexError, TypeError):
                            return "Could not parse the song data."
                    else:
                        return "Error connecting to the Last.fm API."
        except Exception as e:
            print(f"Last.fm API error: {e}")
            return "An error occurred while fetching the song."

    async def setup(self):
        """Performs async setup for the cog, fetching the bot's own user ID."""
        try:
            # Get the bot's own user info so it doesn't reply to its own messages
            bot_user_data = [user async for user in self.twitch.get_users()]
            if not bot_user_data:
                raise Exception("Could not get bot's user information for SongCog.")
            self.bot_login_name = bot_user_data[0].login.lower()
            print("  - SongCog setup complete.")
        except Exception as e:
            print(f"Error during SongCog setup: {e}")
            raise e

    async def on_message(self, msg: ChatMessage):
        """Handles the !song command for all connected channels."""
        # Ignore messages from the bot itself or messages that don't start with !
        if msg.user.name.lower() == self.bot_login_name or not msg.text.startswith('!'):
            return

        parts = msg.text.lower().split()
        command = parts[0]

        if command == '!song':
            channel_name = msg.room.name.lower()
            current_config = self.channel_data.get(channel_name)

            if not current_config:
                return # Channel not configured

            # Grab the Last.fm username directly from this channel's config.json data
            lastfm_username = current_config.get('lastfm_username')
            
            if not lastfm_username:
                await self.chat.send_message(channel_name, "No Last.fm account is linked to this channel.")
                return
            
            # Fetch the song via API and post it to chat
            song_response = await self.get_current_song(lastfm_username)
            await self.chat.send_message(channel_name, song_response)

# This setup function is called by your main script to load this specific cog
async def setup(twitch: Twitch, chat: Chat, channel_configs: List[Dict]):
    """Initializes and registers the cog with the bot."""
    cog = Song(twitch, chat, channel_configs)
    await cog.setup()
    chat.register_event(cog.event_name, cog.on_message)
    print("SongCog loaded and message handler registered.")