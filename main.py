import asyncio
import os
import importlib
import json
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator, refresh_access_token
from twitchAPI.type import AuthScope
from twitchAPI.chat import Chat

# --- Configuration ---
# Your Client ID and Secret should be in a .env file
# Channel-specific settings are now in config.json

# Load environment variables for credentials
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("dotenv library not found, continuing without it.")

APP_ID = os.getenv('CLIENT_ID')
APP_SECRET = os.getenv('CLIENT_SECRET')
TOKEN_FILE = 'my_token.json'
CONFIG_FILE = 'config.json'

# Define the necessary scopes for your bot.
USER_SCOPES = [
    AuthScope.CHAT_READ,
    AuthScope.CHAT_EDIT,
    AuthScope.MODERATOR_MANAGE_BANNED_USERS,
    # Add other scopes as needed...
]


async def on_token_refresh(token: str, refresh: str):
    """Callback for when a token is refreshed, saves the new token."""
    print('Token was refreshed! Saving new token to file.')
    with open(TOKEN_FILE, 'w') as f:
        json.dump({'token': token, 'refresh': refresh}, f, indent=4)


async def run_bot():
    """
    Sets up the Twitch API, authenticates, loads cogs, and starts the chat bot.
    """
    # --- Load Configuration from JSON ---
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Configuration file '{CONFIG_FILE}' not found.")
        return
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    # Extract channel names to join from the config
    channel_configs = config.get('channels', [])
    if not channel_configs:
        print("Error: No channels configured in config.json")
        return
    
    target_channels = [ch['name'] for ch in channel_configs]

    if not all([APP_ID, APP_SECRET]):
        print("Error: CLIENT_ID or CLIENT_SECRET environment variables are not set.")
        return

    # Initialize the Twitch API client
    twitch = await Twitch(APP_ID, APP_SECRET)

    # --- Authentication (no changes here) ---
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

    # --- Load Cogs Dynamically ---
    # --- Load Cogs Dynamically ---
    print("Loading cogs...")
    
    # Store cog instances here to handle dependencies, e.g., AdminCog -> MalLinkCog
    loaded_cogs = {}

    # Define the order to load cogs in, so dependencies are met
    # The cog with the data (admin) must be loaded before the one that needs it (mal_link)
    cog_load_order = ['admin', 'mal_link', 'blacklist', 'commands', 'fun']

    for cog_name in cog_load_order:
        filename = f"{cog_name}.py"
        module_name = f'cogs.{cog_name}'
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, 'setup'):
                # Check for specific dependencies
                if cog_name == 'mal_link':
                    admin_instance = loaded_cogs.get('admin')
                    cog_instance = await module.setup(twitch, chat, channel_configs, admin_cog_instance=admin_instance)
                else:
                    cog_instance = await module.setup(twitch, chat, channel_configs)
                
                # Store the created cog instance
                if cog_instance:
                    loaded_cogs[cog_name] = cog_instance

                print(f"  - Successfully loaded cog: {cog_name}")
            else:
                print(f"  - Warning: Cog {cog_name} has no setup function.")
        except ImportError:
            print(f"  - Skipping {cog_name}, file not found.")
        except Exception as e:
            print(f"  - Failed to load cog {cog_name}: {e}")

    # Start the chat connection
    chat.start()

    # --- Join all channels specified in the config ---
    print(f"Joining channels: {', '.join(target_channels)}")
    await chat.join_room(target_channels)
    print("Bot is running. Press Ctrl+C to shut down.")

    # Keep the bot running indefinitely
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("Bot is shutting down.")
    finally:
        await chat.stop()
        await twitch.close()
        print("Bot has been shut down.")


if __name__ == "__main__":
    asyncio.run(run_bot())