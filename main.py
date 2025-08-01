import asyncio
import os
import importlib
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope
from twitchAPI.chat import Chat

# --- Configuration ---
# It's recommended to use environment variables for your credentials.
# Create a .env file in the same directory with these lines:
# CLIENT_ID="your_client_id"
# CLIENT_SECRET="your_client_secret"
# TARGET_CHANNEL="your_twitch_channel_name"
# DISCORD_WEBHOOK_URL="your_discord_webhook_url"
# DISCORD_MOD_ROLE_ID="your_moderator_role_id"

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("dotenv library not found, please install with 'pip install python-dotenv'")
    print("Continuing without it, make sure environment variables are set manually.")

APP_ID = os.environ.get('CLIENT_ID')
APP_SECRET = os.environ.get('CLIENT_SECRET')
TARGET_CHANNEL = os.environ.get('TARGET_CHANNEL')

# Define the necessary scopes for your bot.
USER_SCOPES = [
    AuthScope.CHAT_READ,
    AuthScope.CHAT_EDIT,
    AuthScope.MODERATOR_MANAGE_BANNED_USERS
]

async def run_bot():
    """
    Sets up the Twitch API, authenticates, loads cogs, and starts the chat bot.
    """
    if not all([APP_ID, APP_SECRET, TARGET_CHANNEL]):
        print("Error: CLIENT_ID, CLIENT_SECRET, or TARGET_CHANNEL environment variables are not set.")
        return

    # Initialize the Twitch API client
    twitch = await Twitch(APP_ID, APP_SECRET)

    # Authenticate and get user token
    auth = UserAuthenticator(twitch, USER_SCOPES)
    token, refresh_token = await auth.authenticate()
    await twitch.set_user_authentication(token, USER_SCOPES, refresh_token)

    # Create the Chat instance
    chat = await Chat(twitch)

    # --- Load Cogs Dynamically ---
    print("Loading cogs...")
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('__'):
            module_name = f'cogs.{filename[:-3]}'
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, 'setup'):
                    await module.setup(twitch, chat, TARGET_CHANNEL)
                    print(f"  - Successfully loaded cog: {filename[:-3]}")
                else:
                    print(f"  - Warning: Cog {filename[:-3]} has no setup function.")
            except Exception as e:
                print(f"  - Failed to load cog {filename[:-3]}: {e}")

    # Start the chat connection
    chat.start()

    # Join the channel and start listening for messages
    print(f"Joining channel: {TARGET_CHANNEL}")
    await chat.join_room(TARGET_CHANNEL)
    print("Bot is running. Press Ctrl+C to shut down.")

    # Keep the bot running indefinitely
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("Bot is shutting down.")
    finally:
        # Clean up resources
        await chat.stop()
        await twitch.close()
        print("Bot has been shut down.")

if __name__ == "__main__":
    asyncio.run(run_bot())
