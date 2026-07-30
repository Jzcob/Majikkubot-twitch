import discord
from discord.ext import commands
import asyncio
import os
import importlib
import json
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator, refresh_access_token
from twitchAPI.type import AuthScope
from twitchAPI.chat import Chat
import traceback

# --- Configuration ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("dotenv library not found, continuing without it.")

APP_ID = os.getenv('CLIENT_ID')
APP_SECRET = os.getenv('CLIENT_SECRET')
TOKEN_FILE = 'my_token.json'
CONFIG_FILE = 'config.json'

USER_SCOPES = [
    AuthScope.CHAT_READ,
    AuthScope.CHAT_EDIT,
    AuthScope.MODERATOR_MANAGE_BANNED_USERS,
]


async def on_token_refresh(token: str, refresh: str):
    """Callback for when a token is refreshed, saves the new token."""
    print('Token was refreshed! Saving new token to file.')
    with open(TOKEN_FILE, 'w') as f:
        json.dump({'token': token, 'refresh': refresh}, f, indent=4)


async def run_twitch_bot():
    """Sets up Twitch API, authenticates, loads cogs, and starts chat bot."""
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Configuration file '{CONFIG_FILE}' not found.")
        return
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    channel_configs = config.get('channels', [])
    if not channel_configs:
        print("Error: No channels configured in config.json")
        return
    
    target_channels = [ch['name'] for ch in channel_configs]

    if not all([APP_ID, APP_SECRET]):
        print("Error: CLIENT_ID or CLIENT_SECRET environment variables are not set.")
        return

    twitch = await Twitch(APP_ID, APP_SECRET)

    if os.path.exists(TOKEN_FILE):
        print("Found token file, attempting to refresh...")
        with open(TOKEN_FILE, 'r') as f:
            creds = json.load(f)
        try:
            token, refresh_token = await refresh_access_token(creds['refresh'], APP_ID, APP_SECRET)
            print("Token refreshed successfully.")
            await on_token_refresh(token, refresh_token)
        except Exception as e:
            print(f"Failed to refresh token: {e}. Please re-authenticate.")
            token, refresh_token = None, None
    else:
        token, refresh_token = None, None

    if token is None:
        print("No valid token found, starting authentication...")
        auth = UserAuthenticator(twitch, USER_SCOPES, force_verify=False)
        token, refresh_token = await auth.authenticate()
        await on_token_refresh(token, refresh_token)

    await twitch.set_user_authentication(token, USER_SCOPES, refresh_token)
    chat = await Chat(twitch)

    # --- Load Twitch Cogs Dynamically ---
    print("Loading Twitch cogs...")
    loaded_cogs = {}
    cog_directory = "./twitch_cogs"

    if os.path.exists(cog_directory):
        filenames = [
            f for f in os.listdir(cog_directory)
            if f.endswith('.py') and not f.startswith('__')
        ]

        # Prioritize 'admin.py' so dependent cogs like 'mal_link' receive its instance
        if 'admin.py' in filenames:
            filenames.remove('admin.py')
            filenames.insert(0, 'admin.py')

        for filename in filenames:
            cog_name = filename[:-3]
            module_name = f'twitch_cogs.{cog_name}'
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, 'setup'):
                    if cog_name == 'mal_link':
                        admin_instance = loaded_cogs.get('admin')
                        cog_instance = await module.setup(twitch, chat, channel_configs, admin_cog_instance=admin_instance)
                    else:
                        cog_instance = await module.setup(twitch, chat, channel_configs)
                    
                    if cog_instance:
                        loaded_cogs[cog_name] = cog_instance

                    print(f"  - Successfully loaded cog: {cog_name}")
                else:
                    print(f"  - Warning: Cog {cog_name} has no setup function.")
            except Exception as e:
                print(f"  - Failed to load cog {cog_name}: {e}")
    else:
        print(f"Warning: Directory '{cog_directory}' not found.")

    chat.start()

    print(f"Joining channels: {', '.join(target_channels)}")
    await chat.join_room(target_channels)
    print("Twitch bot is running.")

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await chat.stop()
        await twitch.close()
        print("Twitch bot has shut down.")


class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        print("Loading discord cogs...")
        cog_directory = ["./discord_cogs"]

        for directory in cog_directory:
            if not os.path.exists(directory):
                print(f"Warning: Directory '{directory}' not found.")
                continue
                
            for filename in os.listdir(directory):
                if filename.endswith('.py') and not filename.startswith('__'):
                    path = directory.replace('./', '').replace('/', '.')
                    cog_path = f"{path}.{filename[:-3]}"
                    
                    try:
                        await self.load_extension(cog_path)
                        print(f'✅ Loaded: `{cog_path}`')
                    except Exception as e:
                        print(f"❌ Failed to load cog {cog_path}: {e}")
                        traceback.print_exc()
        print("--------------------")

intents = discord.Intents.default()
intents.message_content = True
intents.auto_moderation_configuration = True
intents.reactions = True
intents.members = False 

bot = MyBot(command_prefix='!', intents=intents, help_command=None)


def is_owner(ctx):
    owner_id = os.getenv("BOT_OWNER_ID")
    return owner_id is not None and ctx.author.id == int(owner_id)


@bot.command()
async def sync(ctx) -> None:
    if is_owner(ctx):
        try:
            fmt = await ctx.bot.tree.sync()
            print(f"Synced {len(fmt)} commands.")
            embed = discord.Embed(title="Synced", description=f"Synced {len(fmt)} commands.", color=0x00ff00)
            await ctx.send(embed=embed)
        except Exception as e:
            print(e)
            await ctx.send(f"Error syncing commands: {e}")
    else:
        embed = discord.Embed(title="Error", description="This is a bot admin command restricted to only the bot owner.", color=0xff0000)
        await ctx.send(embed=embed)


@bot.command()
async def syncserver(ctx) -> None:
    if is_owner(ctx):
        try:
            fmt = await ctx.bot.tree.sync(guild=ctx.guild)
            print(f"Synced {len(fmt)} commands: {[c.name for c in fmt]}")
            embed = discord.Embed(title="Synced", description=f"Synced {len(fmt)} commands to this server.", color=0x00ff00)
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"Sync Error: {e}")
            await ctx.send(f"Sync Error: {e}")
    else:
        embed = discord.Embed(title="Error", description="This is a bot admin command restricted to only the bot owner.", color=0xff0000)
        await ctx.send(embed=embed)


@bot.event
async def on_ready():
    print(f"Logged on as {bot.user}")
    print(f"Bot is ready and connected to {len(bot.guilds)} servers.")


async def main():
    discord_token = os.getenv("BOT_TOKEN")
    if not discord_token:
        print("Error: BOT_TOKEN environment variable not set.")
        return

    # Run both bots concurrently
    await asyncio.gather(
        run_twitch_bot(),
        bot.start(discord_token)
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down bots...")
    except Exception as e:
        print(f"Error occurred: {e}")