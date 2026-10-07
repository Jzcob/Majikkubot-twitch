import discord
import json
import os
import traceback
from discord import app_commands
from discord.ext import commands, tasks
from twitchAPI.twitch import Twitch

CONFIG_FILE = "config.json"

class StreamingNotifier(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twitch = None
        self.live_streamers = set()

    def load_channels(self):
        if not os.path.exists(CONFIG_FILE):
            return []
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [c for c in data.get("channels", []) if isinstance(c, dict) and c.get("name")]
        except Exception as e:
            print(f"StreamingNotifier config error: {type(e).__name__}: {e}")
            return []

    async def cog_load(self):
        app_id = os.getenv("CLIENT_ID")
        app_secret = os.getenv("CLIENT_SECRET")
        if not app_id or not app_secret:
            print("Warning: CLIENT_ID or CLIENT_SECRET missing; streaming.py monitor disabled.")
            return
        try:
            self.twitch = await Twitch(app_id, app_secret)

            # IMPORTANT: Do not wait for bot readiness inside cog_load().
            # setup_hook() is still running while extensions load, so awaiting
            # wait_until_ready() here would deadlock Discord startup.
            if not self.check_streams.is_running():
                self.check_streams.start()

            print("LOADED: `streaming.py` (Twitch Live Monitor active)")
        except Exception as e:
            print(f"Failed to initialize Twitch client in streaming.py: {type(e).__name__}: {e}")
            print(traceback.format_exc())

    async def cog_unload(self):
        if self.check_streams.is_running():
            self.check_streams.cancel()
        if self.twitch:
            await self.twitch.close()

    async def run_stream_check(self, force=False, only_streamer=None):
        if not self.twitch:
            return {"checked": 0, "live": 0, "announced": 0, "errors": 1,
                    "message": "Twitch client is not initialized."}

        channels = self.load_channels()
        if only_streamer:
            wanted = only_streamer.lower().lstrip("@")
            channels = [c for c in channels if c["name"].lower() == wanted]
            if not channels:
                return {"checked": 0, "live": 0, "announced": 0, "errors": 0,
                        "message": f"`{wanted}` is not in config.json."}

        if not channels:
            return {"checked": 0, "live": 0, "announced": 0, "errors": 0,
                    "message": "No Twitch channels are configured."}

        names = [c["name"].lower() for c in channels]
        streams = [s async for s in self.twitch.get_streams(user_login=names)]
        live = {s.user_login.lower(): s for s in streams}
        announced = errors = 0

        for cfg in channels:
            name = cfg["name"].lower()
            if name not in live:
                self.live_streamers.discard(name)
                continue

            was_live = name in self.live_streamers
            self.live_streamers.add(name)
            channel_id = cfg.get("streaming_channel_id")
            if not channel_id:
                print(f"StreamingNotifier: #{name} is live; no streaming_channel_id configured.")
                continue

            if force or not was_live:
                try:
                    await self.send_live_announcement(
                        channel_id, cfg["name"], live[name],
                        cfg.get("streaming_ping_role")
                    )
                    announced += 1
                    print(f"StreamingNotifier: announced #{name} (force={force}).")
                except Exception as e:
                    errors += 1
                    print(f"StreamingNotifier: announcement error for #{name}: {type(e).__name__}: {e}")

        return {"checked": len(channels), "live": len(live), "announced": announced,
                "errors": errors, "message": None}

    @tasks.loop(seconds=60)
    async def check_streams(self):
        try:
            await self.run_stream_check(force=False)
        except Exception:
            print("Error in check_streams loop:")
            print(traceback.format_exc())

    @check_streams.before_loop
    async def before_check_streams(self):
        # Wait until Discord is ready, then PRIME the current live state
        # WITHOUT sending announcements. This prevents an ApolloPanel/container
        # restart from pinging Discord again during the same Twitch stream.
        await self.bot.wait_until_ready()
        print("StreamingNotifier: Discord ready; syncing live state without notifications...")
        try:
            channels = self.load_channels()
            names = [c["name"].lower() for c in channels]
            if names:
                streams = [
                    s async for s in self.twitch.get_streams(user_login=names)
                ]
                self.live_streamers = {
                    s.user_login.lower() for s in streams
                }
                if self.live_streamers:
                    print(
                        "StreamingNotifier startup sync: already live "
                        "(NO Discord ping): "
                        + ", ".join(sorted(self.live_streamers))
                    )
                else:
                    print("StreamingNotifier startup sync: nobody currently live.")
        except Exception:
            print("StreamingNotifier startup state sync failed:")
            print(traceback.format_exc())

    async def send_live_announcement(self, channel_id, streamer_name, stream, ping_role=None):
        try:
            channel_id = int(channel_id)
        except (TypeError, ValueError):
            print(f"Invalid Discord channel ID {channel_id!r} for {streamer_name}")
            return

        target = self.bot.get_channel(channel_id)
        if not target:
            try:
                target = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                print(f"Could not find Discord channel {channel_id} for {streamer_name}: {e}")
                return

        stream_url = f"https://twitch.tv/{streamer_name}"
        embed = discord.Embed(
            title=f"🔴 {streamer_name} is NOW LIVE on Twitch!",
            description=f"**{stream.title}**",
            url=stream_url,
            color=discord.Color.purple()
        )
        embed.add_field(name="Category", value=stream.game_name or "Just Chatting", inline=True)
        embed.add_field(name="Viewers", value=str(stream.viewer_count), inline=True)
        if stream.thumbnail_url:
            thumb = stream.thumbnail_url.replace("{width}", "1280").replace("{height}", "720")
            embed.set_image(url=thumb)

        mention = ""
        if ping_role:
            pr = str(ping_role).strip()
            if pr.isdigit():
                mention = f"Hey <@&{pr}>, "
            elif pr.lower() in ("@everyone", "@here"):
                mention = f"Hey {pr}, "

        await target.send(
            content=f"{mention}**{streamer_name}** is live! Check out the stream: {stream_url}",
            embed=embed
        )

    @app_commands.command(
        name="force-stream-check",
        description="Force a Twitch live check and resend current live announcements."
    )
    @app_commands.describe(
        streamer="Optional Twitch channel. Leave blank to check all configured streamers."
    )
    @app_commands.default_permissions(administrator=True)
    async def force_stream_check(self, interaction: discord.Interaction, streamer: str = None):
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.run_stream_check(force=True, only_streamer=streamer)
            if result["message"]:
                await interaction.followup.send(result["message"], ephemeral=True)
                return
            target = f"`{streamer.lstrip('@')}`" if streamer else "all configured streamers"
            await interaction.followup.send(
                f"✅ Forced Twitch check completed for {target}.\n"
                f"**Checked:** {result['checked']}\n"
                f"**Currently live:** {result['live']}\n"
                f"**Announcements sent:** {result['announced']}\n"
                f"**Errors:** {result['errors']}",
                ephemeral=True
            )
        except Exception as e:
            print(f"Force stream check failed: {type(e).__name__}: {e}")
            print(traceback.format_exc())
            await interaction.followup.send(
                f"❌ Twitch live check failed: `{type(e).__name__}: {e}`",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(StreamingNotifier(bot))
