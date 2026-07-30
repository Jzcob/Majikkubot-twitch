import random
from twitchAPI.chat import Chat, ChatMessage, ChatEvent
from twitchAPI.twitch import Twitch
from typing import List, Dict

# The list of 8-ball responses remains the same
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
    # The __init__ signature is changed to accept the list of configs, but we don't need to store it.
    def __init__(self, twitch: Twitch, chat: Chat, channel_configs: List[Dict]):
        self.twitch = twitch
        self.chat = chat
        self.event_name = ChatEvent.MESSAGE
        self.bot_login_name = None

    async def setup(self):
        """Performs async setup required for the cog. (No changes needed here)"""
        try:
            bot_user_data = [user async for user in self.twitch.get_users()]
            if not bot_user_data:
                raise Exception("Could not get bot's user information for FunCog.")
            self.bot_login_name = bot_user_data[0].login.lower()
        except Exception as e:
            print(f"Error during FunCog setup: {e}")
            raise e

    async def on_message(self, msg: ChatMessage):
        """This function handles messages from all connected channels."""
        if msg.user.name.lower() == self.bot_login_name:
            return

        if not msg.text.startswith('!'):
            return

        # Get the channel where the message originated
        channel_name = msg.room.name

        parts = msg.text.lower().split()
        command = parts[0]
        
        if command == '!8ball':
            # Check if the user actually asked a question
            if len(parts) < 2:
                # Send the reply back to the correct channel
                await self.chat.send_message(channel_name, f"@{msg.user.name}, you need to ask a question! 🤔")
                return
            
            # Pick a random response and send it to the correct channel
            response = random.choice(EIGHT_BALL_RESPONSES)
            await self.chat.send_message(channel_name, f"@{msg.user.name}, {response}")
        
        elif command == '!bald':
            bald_message = f"{msg.user.name} is BALD! 🦲✨"
            await self.chat.send_message(channel_name, bald_message)
        
        elif command.startswith('!diddy'):
            target_user = command[len('!diddy'):].strip()
            if target_user:
                diddy_message = f"{target_user} is a diddy! 🎉"
                await self.chat.send_message(channel_name, diddy_message)
            else:
                await self.chat.send_message(channel_name, "Please specify a user.")


# The main setup function signature is updated to match the main script
async def setup(twitch: Twitch, chat: Chat, channel_configs: List[Dict]):
    """Initializes and registers the cog with the bot."""
    cog = FunCog(twitch, chat, channel_configs)
    await cog.setup()
    chat.register_event(cog.event_name, cog.on_message)
    print("FunCog loaded and message handler registered.")