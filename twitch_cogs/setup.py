import aiomysql
from twitchAPI.chat import Chat, ChatMessage, ChatCommand, ChatEvent
from twitchAPI.twitch import Twitch

# Database connection settings (Best to put these in your .env file)
DB_HOST = "your_mysql_host"
DB_USER = "your_mysql_user"
DB_PASS = "your_mysql_password"
DB_NAME = "your_database_name"

# Define the prompts in order. 
# The tuple contains (Database Column Name, User Prompt, Is Optional)
SETUP_STEPS = [
    ("discord_webhook_mod", "Please paste your Discord Mod Webhook URL.", False),
    ("discord_webhook_log", "Please paste your Discord Log Webhook URL.", False),
    ("discord_mod_role_id", "Please provide your Discord Mod Role ID.", False),
    ("discord_invite_link", "Please paste your Discord Invite Link (or type 'skip').", True),
    ("youtube_channel_link", "Please paste your YouTube Link (or type 'skip').", True),
    ("tiktok_channel_link", "Please paste your TikTok Link (or type 'skip').", True),
]

class SetupManager:
    def __init__(self, chat: Chat):
        self.chat = chat
        # Dictionary to track who is in setup mode: { "channel_name": {"user": "username", "step": 0, "data": {}} }
        self.active_setups = {}

    async def init_db_pool(self):
        """Initializes the connection pool to MySQL."""
        self.pool = await aiomysql.create_pool(
            host=DB_HOST, port=3306,
            user=DB_USER, password=DB_PASS,
            db=DB_NAME, autocommit=True
        )

    async def start_setup(self, cmd: ChatCommand):
        """Triggered by !setup"""
        room = cmd.room.name
        user = cmd.user.name

        # Security check: Ensure only the broadcaster (or admins) can run setup
        if room != user and not cmd.user.badges.get('broadcaster'):
            await self.chat.send_message(room, "Only the broadcaster can run setup.")
            return

        # Initialize the setup session for this channel
        self.active_setups[room] = {
            "user": user,
            "step": 0,
            "data": {}
        }
        
        await self.chat.send_message(room, f"Starting setup! {SETUP_STEPS[0][1]}")

    async def handle_setup_messages(self, msg: ChatMessage):
        """Listens to all messages to catch setup inputs."""
        room = msg.room.name
        user = msg.user.name

        # Ignore if this channel isn't in setup mode, or if the message isn't from the person running setup
        if room not in self.active_setups or self.active_setups[room]["user"] != user:
            return

        # Ignore commands being parsed as setup inputs
        if msg.text.startswith("!"):
            return

        session = self.active_setups[room]
        current_step_index = session["step"]
        column_name, prompt, is_optional = SETUP_STEPS[current_step_index]

        # Handle "skip" for optional fields
        if is_optional and msg.text.strip().lower() == "skip":
            session["data"][column_name] = None
        else:
            session["data"][column_name] = msg.text.strip()

        # Advance to the next step
        session["step"] += 1
        next_step_index = session["step"]

        if next_step_index < len(SETUP_STEPS):
            # Ask the next question
            next_prompt = SETUP_STEPS[next_step_index][1]
            await self.chat.send_message(room, f"Got it. {next_prompt}")
        else:
            # Setup is complete, save to database
            await self.save_to_database(room, session["data"])
            del self.active_setups[room] # Clear the session
            await self.chat.send_message(room, "Setup complete! Your channel configuration has been saved to the database.")

    async def save_to_database(self, channel_name: str, data: dict):
        """Saves the collected data into MySQL."""
        query = """
            INSERT INTO channel_configs 
            (channel_name, discord_webhook_mod, discord_webhook_log, discord_mod_role_id, discord_invite_link, youtube_channel_link, tiktok_channel_link)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            discord_webhook_mod=VALUES(discord_webhook_mod), 
            discord_webhook_log=VALUES(discord_webhook_log),
            discord_mod_role_id=VALUES(discord_mod_role_id),
            discord_invite_link=VALUES(discord_invite_link),
            youtube_channel_link=VALUES(youtube_channel_link),
            tiktok_channel_link=VALUES(tiktok_channel_link)
        """
        values = (
            channel_name,
            data.get("discord_webhook_mod"),
            data.get("discord_webhook_log"),
            data.get("discord_mod_role_id"),
            data.get("discord_invite_link"),
            data.get("youtube_channel_link"),
            data.get("tiktok_channel_link")
        )
        
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, values)


async def setup(twitch: Twitch, chat: Chat, channel_configs: list, **kwargs):
    """Cog setup function"""
    manager = SetupManager(chat)
    await manager.init_db_pool()
    
    # Register the !setup command
    chat.register_command('setup', manager.start_setup)
    
    # Register the message listener to intercept responses
    chat.register_event(ChatEvent.MESSAGE, manager.handle_setup_messages)
    
    return manager