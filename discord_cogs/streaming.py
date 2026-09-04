# Live Streamer Notifier Cog for Majikku Bot
# Periodically checks Twitch streams and posts live alerts to Discord.

import discord
import json
import os
import traceback
import time
from discord.ext import commands, tasks
from twitchAPI.twitch import Twitch

CONFIG_FILE = "config.json"


class StreamingNotifier(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twitch = None
        self.live_streamers = set()  # Tracks currently live channels to prevent spam

    async def cog_load(self):
        """Called automatically when the cog is loaded."""
        app_id = os.getenv("CLIENT_ID")
        app_secret = os.getenv("CLIENT_SECRET")
        if app_id and app_secret:
            try:
                self.twitch = await Twitch(app_id, app_secret)
                self.check_streams.start()
                print("LOADED: `streaming.py` (Twitch Live Monitor active)")
            except Exception as e:
                print(f"Failed to initialize Twitch client in streaming.py: {e}")
        else:
            print("Warning: CLIENT_ID or CLIENT_SECRET missing; streaming.py monitor disabled.")

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        self.check_streams.cancel()
        if self.twitch:
            await self.twitch.close()

    @tasks.loop(seconds=60)
    async def check_streams(self):
        """Checks Twitch stream status every 60 seconds."""
        if not os.path.exists(CONFIG_FILE) or not self.twitch:
            return

        try:
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)

            channels = config_data.get("channels", [])
            if not channels:
                return

            channel_names = [ch["name"].lower() for ch in channels if "name" in ch]
            if not channel_names:
                return

            # Query Twitch API for live streams
            streams = [stream async for stream in self.twitch.get_streams(user_login=channel_names)]
            currently_live = {s.user_login.lower(): s for s in streams}

            for ch_config in channels:
                ch_name = ch_config["name"].lower()
                channel_id = ch_config.get("streaming_channel_id")

                if not channel_id:
                    continue  # Skip channels without a configured Discord alert channel

                if ch_name in currently_live:
                    if ch_name not in self.live_streamers:
                        self.live_streamers.add(ch_name)
                        stream_data = currently_live[ch_name]
                        await self.send_live_announcement(
                            channel_id,
                            ch_config["name"],
                            stream_data,
                            ch_config.get("streaming_ping_role"),
                        )
                else:
                    if ch_name in self.live_streamers:
                        self.live_streamers.remove(ch_name)

        except Exception:
            print("Error in check_streams loop:")
            print(traceback.format_exc())

    @check_streams.before_loop
    async def before_check_streams(self):
        await self.bot.wait_until_ready()

    async def send_live_announcement(self, channel_id: int, streamer_name: str, stream, ping_role=None):
        target_channel = self.bot.get_channel(channel_id)
        if not target_channel:
            try:
                target_channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                print(f"Could not find Discord channel ID {channel_id} for {streamer_name}")
                return

        stream_url = f"https://twitch.tv/{streamer_name}"
        embed = discord.Embed(
            title=f"🔴 {streamer_name} is NOW LIVE on Twitch!",
            description=f"**{stream.title}**",
            url=stream_url,
            color=discord.Color.purple()
        )
        stream.thumbnail_url = stream.thumbnail_url.replace("{width}", "1280").replace("{height}", "720")
        embed.set_thumbnail(url=stream.thumbnail_url)
        embed.add_field(name="Category", value=stream.game_name or "Just Chatting", inline=True)
        embed.add_field(name="Viewers", value=str(stream.viewer_count), inline=True)

        # Build thumbnail URL
        if stream.thumbnail_url:
            thumb = stream.thumbnail_url.replace("{width}", "1280").replace("{height}", "720")
            embed.set_image(url=thumb)

        mention_text = ""
        if ping_role:
            # Allow numeric role IDs or literal @everyone/@here mentions
            pr = str(ping_role)
            if pr.isdigit():
                mention_text = f"Hey <@&{pr}>, "
            elif pr.lower() in ("@everyone", "@here"):
                mention_text = f"Hey {pr}, "
            else:
                # Fallback: treat as role ID string
                mention_text = f"Hey <@&{pr}>, "

        content = (
            f"{mention_text}**{streamer_name}** is live! Check out the stream: {stream_url}"
        )
        await target_channel.send(content=content, embed=embed)


async def setup(bot):
    await bot.add_cog(StreamingNotifier(bot))