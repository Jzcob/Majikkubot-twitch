import random
from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch

# A list of 50 possible responses for the 8-ball command
EIGHT_BALL_RESPONSES = [
    # Positive Responses
    "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes, definitely.",
    "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.",
    "Yes.", "Signs point to yes.", "The stars are aligned in your favor.", "Go for it!",
    "Absolutely!", "The outlook is promising.", "I have a good feeling about this.",
    "The answer is a resounding YES!", "All signs point to a positive outcome.",
    "You can count on it.", "Prospects are excellent.", "No doubt about it.",

    # Neutral / Non-Committal Responses
    "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
    "Cannot predict now.", "Concentrate and ask again.", "The answer is unclear at this time.",
    "My sources are saying maybe.", "Let me think on that.", "The future is cloudy.",
    "I'm not sure, ask a mod.", "Perhaps.", "It's a possibility.",
    "The outcome is uncertain.", "Let the universe decide.", "Only time will tell.",

    # Negative Responses
    "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.",
    "Very doubtful.", "I wouldn't bet on it.", "The answer is no.", "Definitely not.",
    "The spirits say no.", "Not a chance.", "I advise against it.",
    "The odds are not in your favor.", "Highly unlikely.", "My answer is a firm NO.",
    "Forget about it."
]

class FunCog:
    def __init__(self, twitch: Twitch, chat: Chat, target_channel: str):
        self.twitch = twitch
        self.chat = chat
        self.target_channel = target_channel
        self.event_name = ChatEvent.MESSAGE # The event this cog listens to

        # To be populated by the setup method
        self.bot_login_name = None

    async def setup(self):
        """Performs async setup required for the cog."""
        try:
            # Get authenticated bot user info to prevent the bot from replying to itself
            bot_user_gen = self.twitch.get_users()
            bot_user_data = [user async for user in bot_user_gen]
            if not bot_user_data:
                raise Exception("Could not get bot's user information for FunCog.")
            self.bot_login_name = bot_user_data[0].login.lower()
            
        except Exception as e:
            print(f"Error during FunCog setup: {e}")
            raise e

    async def on_message(self, msg: ChatMessage):
        """This function is called by the Chat instance for each new message."""
        # The bot should not react to its own messages
        if msg.user.name.lower() == self.bot_login_name:
            return

        # --- Command Handling ---
        if not msg.text.startswith('!'):
            return

        parts = msg.text.lower().split()
        command = parts[0]
        
        if command == '!8ball':
            # Check if the user actually asked a question
            if len(parts) < 2:
                await self.chat.send_message(self.target_channel, f"@{msg.user.name}, you need to ask a question!")
                return
            
            # Pick a random response and send it
            response = random.choice(EIGHT_BALL_RESPONSES)
            await self.chat.send_message(self.target_channel, f"@{msg.user.name}, {response}")


# This setup function is called by main.py to load the cog
async def setup(twitch: Twitch, chat: Chat, target_channel: str):
    """Initializes and registers the cog with the bot."""
    cog = FunCog(twitch, chat, target_channel)
    await cog.setup()
    chat.register_event(cog.event_name, cog.on_message)
