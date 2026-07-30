# Leveling Cog for Majikku Bot
# Stores leveling data locally in levels.json per guild.

import discord
import json
import os
import random
import traceback
from discord import app_commands
from discord.ext import commands

DB_FILE = "levels.json"

# Level XP thresholds (Level 1 to 20)
XP_LIMITS = [
    150.0, 225.0, 337.5, 506.25, 759.38, 1139.06, 1708.59, 2562.89, 
    3844.34, 5766.5, 8649.76, 12974.63, 19461.95, 29192.93, 43789.39, 
    65684.08, 98526.13, 147789.19, 221683.78, 332525.67
]

# --- JSON Helpers ---

def load_db() -> dict:
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump({}, f, indent=4)
        return {}
    with open(DB_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_db(data: dict) -> None:
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_user_data(data: dict, guild_id: int, user_id: int) -> dict:
    gid = str(guild_id)
    uid = str(user_id)
    if gid not in data:
        data[gid] = {}
    if uid not in data[gid]:
        data[gid][uid] = {"level": 0, "xp": 0.0}
    return data[gid][uid]


class ConfirmReset(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=60)
        self.guild_id = guild_id

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.red, custom_id="confirm_reset_levels")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            data = load_db()
            gid = str(self.guild_id)
            data[gid] = {}
            save_db(data)

            button.disabled = True
            await interaction.message.edit(view=self)
            await interaction.response.send_message("All server XP levels have been reset.", ephemeral=True)
        except Exception:
            print(traceback.format_exc())
            await interaction.response.send_message("An error occurred while resetting levels.", ephemeral=True)


class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("LOADED: `leveling.py` (JSON Edition)")

    @app_commands.command(name="reset-levels", description="Resets all XP levels in this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_levels(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Are you sure you want to reset all user levels in this server? This action cannot be undone.",
            view=ConfirmReset(interaction.guild.id),
            ephemeral=True
        )

    @app_commands.command(name="reset-member-level", description="Resets the XP and level of a specified user.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_member_level(self, interaction: discord.Interaction, user: discord.Member):
        try:
            data = load_db()
            u_data = get_user_data(data, interaction.guild.id, user.id)
            u_data["level"] = 0
            u_data["xp"] = 0.0
            save_db(data)
            await interaction.response.send_message(f"Reset leveling data for {user.mention}.")
        except Exception:
            print(traceback.format_exc())
            await interaction.response.send_message("An error occurred while resetting the user's level.", ephemeral=True)

    @app_commands.command(name="set-member-level", description="Set the level of a specified user.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_member_level(self, interaction: discord.Interaction, user: discord.Member, level: int):
        if level < 1 or level > len(XP_LIMITS):
            return await interaction.response.send_message(f"Level must be between 1 and {len(XP_LIMITS)}.", ephemeral=True)

        try:
            data = load_db()
            u_data = get_user_data(data, interaction.guild.id, user.id)
            u_data["level"] = level
            u_data["xp"] = XP_LIMITS[level - 1]
            save_db(data)
            await interaction.response.send_message(f"Set {user.mention}'s level to **{level}** (XP: {XP_LIMITS[level - 1]:,.2f}).")
        except Exception:
            print(traceback.format_exc())
            await interaction.response.send_message("An error occurred while setting the level.", ephemeral=True)

    @app_commands.command(name="level", description="Check your current level and XP.")
    async def level(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        try:
            data = load_db()
            u_data = get_user_data(data, interaction.guild.id, target.id)

            embed = discord.Embed(color=discord.Color.blue())
            avatar_url = target.avatar.url if target.avatar else target.default_avatar.url
            embed.set_author(name=f"{target.name}'s Level", icon_url=avatar_url)
            embed.add_field(name="__Level__", value=str(u_data["level"]))
            embed.add_field(name="__XP__", value=f"{u_data['xp']:,.2f}")

            await interaction.response.send_message(embed=embed)
        except Exception:
            print(traceback.format_exc())
            await interaction.response.send_message("Could not retrieve level information.", ephemeral=True)

    @app_commands.command(name="level-leaderboard", description="Displays the leveling leaderboard for this server.")
    async def level_leaderboard(self, interaction: discord.Interaction):
        try:
            data = load_db()
            gid = str(interaction.guild.id)
            guild_data = data.get(gid, {})

            if not guild_data:
                return await interaction.response.send_message("The leaderboard is empty!", ephemeral=True)

            # Sort users by Level DESC, then XP DESC
            sorted_users = sorted(
                guild_data.items(),
                key=lambda x: (x["level"], x["xp"]),
                reverse=True
            )[:10]

            embed = discord.Embed(title=f"{interaction.guild.name} Level Leaderboard", color=discord.Color.gold())
            description = []

            for i, (uid, stats) in enumerate(sorted_users, 1):
                user = self.bot.get_user(int(uid)) or await self.bot.fetch_user(int(uid))
                mention = user.mention if user else f"User `{uid}`"
                description.append(f"**{i}.** {mention} - Level: **{stats['level']}** | XP: **{stats['xp']:,.2f}**")

            embed.description = "\n".join(description)
            await interaction.response.send_message(embed=embed)
        except Exception:
            print(traceback.format_exc())
            await interaction.response.send_message("An error occurred while fetching the leaderboard.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        try:
            data = load_db()
            u_data = get_user_data(data, message.guild.id, message.author.id)

            current_level = u_data["level"]
            current_xp = u_data["xp"]

            xp_add = round(random.uniform(1.0, 3.0), 2)
            new_xp = round(current_xp + xp_add, 2)
            new_level = current_level

            if current_level < len(XP_LIMITS) and new_xp >= XP_LIMITS[current_level]:
                new_level += 1
                await message.channel.send(f"🎉 {message.author.mention} has leveled up to **Level {new_level}**!")

            u_data["level"] = new_level
            u_data["xp"] = new_xp
            save_db(data)
        except Exception:
            print(traceback.format_exc())


async def setup(bot):
    await bot.add_cog(Levels(bot))