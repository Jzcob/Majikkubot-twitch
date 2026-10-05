            try:
                async for user in self.twitch.get_users(logins=channel_names):
                    self.broadcaster_ids[user.login.lower()] = user.id
                print(f"  - FollowageCog cached {len(self.broadcaster_ids)} broadcaster ID(s).")
            except Exception as e:
                print(f"FollowageCog broadcaster lookup error: {type(e).__name__}: {e}")

    @staticmethod
    def format_followage(followed_at: datetime) -> str:
        if followed_at.tzinfo is None:
            followed_at = followed_at.replace(tzinfo=timezone.utc)

        diff = relativedelta(datetime.now(timezone.utc), followed_at)
        parts = []

        if diff.years:
            parts.append(f"{diff.years} year{'s' if diff.years != 1 else ''}")
        if diff.months:
            parts.append(f"{diff.months} month{'s' if diff.months != 1 else ''}")
        if diff.days:
            parts.append(f"{diff.days} day{'s' if diff.days != 1 else ''}")

        if not parts:
            if diff.hours:
                parts.append(f"{diff.hours} hour{'s' if diff.hours != 1 else ''}")
            elif diff.minutes:
                parts.append(f"{diff.minutes} minute{'s' if diff.minutes != 1 else ''}")
            else:
                parts.append("less than a minute")

        return ", ".join(parts)

    async def on_message(self, msg: ChatMessage):
        if self.bot_login_name and msg.user.name.lower() == self.bot_login_name:
            return
        if not msg.text.startswith("!"):
            return

        parts = msg.text.strip().split()
        if not parts or parts[0].lower() != "!followage":
            return

        channel_name = msg.room.name.lower()
        user_name = msg.user.name
        user_id = str(msg.user.id)

        try:
            broadcaster_id = self.broadcaster_ids.get(channel_name)

            if not broadcaster_id:
                broadcasters = [
                    user async for user in self.twitch.get_users(logins=[channel_name])
                ]
                if not broadcasters:
                    await self.chat.send_message(
                        channel_name,
                        f"@{user_name}, I couldn't find this channel on Twitch."
                    )
                    return

                broadcaster_id = broadcasters[0].id
                self.broadcaster_ids[channel_name] = broadcaster_id

            # Current twitchAPI returns ChannelFollowersResult here.
            # It must be awaited rather than used with "async for".
            result = await self.twitch.get_channel_followers(
                broadcaster_id=str(broadcaster_id),
                user_id=user_id,
                first=1
            )

            followers = list(result)

            if not followers:
                await self.chat.send_message(
                    channel_name,
                    f"@{user_name}, you are not currently following this channel!"
                )
                return

            time_string = self.format_followage(followers[0].followed_at)

            await self.chat.send_message(
                channel_name,
                f"@{user_name} has been following for {time_string}!"
            )

        except Exception as e:
            # Detailed console output is intentional so Twitch auth/scope
            # failures can actually be diagnosed.
            print(
                f"Followage API error in #{channel_name} for "
                f"{user_name} ({user_id}): {type(e).__name__}: {e}"
            )

            error_name = type(e).__name__.lower()
            error_text = str(e).lower()

            if (
                "scope" in error_name
                or "scope" in error_text
                or "unauthorized" in error_name
                or "unauthorized" in error_text
                or "401" in error_text
            ):
                await self.chat.send_message(
                    channel_name,
                    f"@{user_name}, followage isn't authorized for this channel yet."
                )
            else:
                await self.chat.send_message(
                    channel_name,
                    f"@{user_name}, I ran into an error checking your follow date."
                )


async def setup(twitch: Twitch, chat: Chat, channel_configs: List[Dict], **kwargs):
    cog = FollowageCog(twitch, chat, channel_configs)
    await cog.setup()
    chat.register_event(cog.event_name, cog.on_message)
    print("  - FollowageCog fully initialized.")
    return cog
