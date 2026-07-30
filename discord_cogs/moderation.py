# Moderation Cog for Majikku Bot
# Supports multi-server operation using local JSON storage.

import discord
import json
import os
import traceback
from datetime import datetime as dt, timedelta as td
from discord import app_commands
from discord.ext import commands

DB_FILE = "punishments.json"

DURATION_MAP = {
    "6h": td(hours=6),
    "1d": td(days=1),
    "3d": td(days=3),
    "1w": td(weeks=1),
    "2w": td(weeks=2),
    "3w": td(weeks=3),
    "1m": td(weeks=4),
}

# --- JSON Database Helpers ---

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

def get_user_record(data: dict, guild_id: int, member_id: int) -> dict:
    gid = str(guild_id)
    uid = str(member_id)
    if gid not in data:
        data[gid] = {}
    if uid not in data[gid]:
        data[gid][uid] = {
            "info": {"punished": False},
            "punishments": {
                "warns": [],
                "timeouts": [],
                "bans": [],
                "notes": []
            }
        }
    return data[gid][uid]

def check_punishments(record: dict) -> bool:
    p = record.get("punishments", {})
    return any(len(p.get(k, [])) > 0 for k in ["warns", "timeouts", "bans", "notes"])

def get_timestamps():
    now = dt.now()
    return now.strftime("%b %d, %Y"), now.strftime("%d/%m/%Y %H:%M:%S")

def find_mod_log_channel(guild: discord.Guild):
    for name in ["mod-logs", "mod-log", "logs", "moderator-logs"]:
        channel = discord.utils.get(guild.text_channels, name=name)
        if channel:
            return channel
    return None


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("LOADED: `punish.py` (Public Edition)")

    async def handle_error(self, interaction: discord.Interaction, exc: Exception):
        print(f"Error in command {interaction.command.name if interaction.command else 'Unknown'}:\n{traceback.format_exc()}")
        msg = "An error occurred while processing this command. The issue has been logged."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    def can_target_member(self, interaction: discord.Interaction, member: discord.Member) -> tuple[bool, str]:
        if member.id == interaction.user.id:
            return False, "You cannot execute this command on yourself!"
        if member.id == self.bot.user.id:
            return False, "You cannot execute this command on the bot!"
        if member.id == interaction.guild.owner_id:
            return False, "You cannot execute this command on the server owner!"
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return False, "You cannot moderate someone with a role equal to or higher than yours!"
        return True, ""

    # --- Warn Command ---
    @app_commands.command(name="warn", description="Warns a user in the server.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str, evidence: discord.Attachment = None):
        try:
            allowed, err_msg = self.can_target_member(interaction, member)
            if not allowed:
                return await interaction.response.send_message(err_msg, ephemeral=True)

            time_fmt, dt_str = get_timestamps()
            data = load_db()
            record = get_user_record(data, interaction.guild.id, member.id)

            record["info"]["punished"] = True
            entry = {
                "date": time_fmt,
                "staff": str(interaction.user.id),
                "reason": reason
            }
            if evidence:
                entry["evidence"] = evidence.url

            record["punishments"]["warns"].append(entry)
            save_db(data)

            embed = discord.Embed(title=f"{member.name} was warned", color=discord.Color.gold())
            embed.add_field(name="Punished By", value=interaction.user.mention, inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Time", value=dt_str, inline=False)
            if evidence:
                embed.set_image(url=evidence.url)

            user_embed = discord.Embed(title=f"You have been warned in `{interaction.guild.name}`", color=discord.Color.gold())
            user_embed.add_field(name="Reason", value=reason, inline=False)
            user_embed.add_field(name="Time", value=dt_str, inline=False)
            if evidence:
                user_embed.set_image(url=evidence.url)
            user_embed.set_footer(text="If you feel this was a mistake, please contact server staff.")

            await interaction.response.send_message(embed=embed)

            mod_logs = find_mod_log_channel(interaction.guild)
            try:
                await member.send(embed=user_embed)
            except Exception:
                if mod_logs:
                    await mod_logs.send(f"Unable to DM {member.mention} about their warn.")
            if mod_logs:
                await mod_logs.send(embed=embed)

        except Exception as e:
            await self.handle_error(interaction, e)

    # --- Timeout Command ---
    @app_commands.command(name="timeout", description="Times out a user in the server.")
    @app_commands.describe(duration="How long should the timeout be?")
    @app_commands.choices(duration=[
        app_commands.Choice(name='6 hours', value='6h'),
        app_commands.Choice(name='1 day', value='1d'),
        app_commands.Choice(name='3 days', value='3d'),
        app_commands.Choice(name='1 week', value='1w'),
        app_commands.Choice(name='2 weeks', value='2w'),
        app_commands.Choice(name='3 weeks', value='3w'),
        app_commands.Choice(name='1 month', value='1m'),
    ])
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: app_commands.Choice[str], reason: str, evidence: discord.Attachment = None):
        try:
            if member.is_timed_out():
                return await interaction.response.send_message("This user is already timed out!", ephemeral=True)

            allowed, err_msg = self.can_target_member(interaction, member)
            if not allowed:
                return await interaction.response.send_message(err_msg, ephemeral=True)

            punishment_duration = DURATION_MAP.get(duration.value)
            if not punishment_duration:
                return await interaction.response.send_message("Invalid duration!", ephemeral=True)

            time_fmt, dt_str = get_timestamps()
            data = load_db()
            record = get_user_record(data, interaction.guild.id, member.id)

            record["info"]["punished"] = True
            entry = {
                "date": time_fmt,
                "staff": str(interaction.user.id),
                "reason": reason,
                "duration": duration.name
            }
            if evidence:
                entry["evidence"] = evidence.url

            record["punishments"]["timeouts"].append(entry)
            save_db(data)

            await member.timeout(punishment_duration, reason=reason)

            embed = discord.Embed(title=f"`{member.name}` was timed out", color=discord.Color.orange())
            embed.add_field(name="Punished By", value=interaction.user.mention, inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Duration", value=duration.name, inline=False)
            embed.add_field(name="Time", value=dt_str, inline=False)
            if evidence:
                embed.set_image(url=evidence.url)

            user_embed = discord.Embed(title=f"You have been timed out in `{interaction.guild.name}`", color=discord.Color.orange())
            user_embed.add_field(name="Reason", value=reason, inline=False)
            user_embed.add_field(name="Duration", value=duration.name, inline=False)
            user_embed.add_field(name="Time", value=dt_str, inline=False)
            if evidence:
                user_embed.set_image(url=evidence.url)

            await interaction.response.send_message(embed=embed)

            mod_logs = find_mod_log_channel(interaction.guild)
            try:
                await member.send(embed=user_embed)
            except Exception:
                if mod_logs:
                    await mod_logs.send(f"Unable to DM {member.mention} about their timeout.")
            if mod_logs:
                await mod_logs.send(embed=embed)

        except Exception as e:
            await self.handle_error(interaction, e)

    # --- Ban Command ---
    @app_commands.command(name="ban", description="Bans a user from the server.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str, evidence: discord.Attachment = None):
        try:
            allowed, err_msg = self.can_target_member(interaction, member)
            if not allowed:
                return await interaction.response.send_message(err_msg, ephemeral=True)

            time_fmt, dt_str = get_timestamps()
            data = load_db()
            record = get_user_record(data, interaction.guild.id, member.id)

            record["info"]["punished"] = True
            entry = {
                "date": time_fmt,
                "staff": str(interaction.user.id),
                "reason": reason
            }
            if evidence:
                entry["evidence"] = evidence.url

            record["punishments"]["bans"].append(entry)
            save_db(data)

            embed = discord.Embed(title=f"`{member.name}` was banned", color=discord.Color.red())
            embed.add_field(name="Punished By", value=interaction.user.mention, inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Time", value=dt_str, inline=False)
            if evidence:
                embed.set_image(url=evidence.url)

            await member.ban(reason=reason)
            await interaction.response.send_message(embed=embed)

            mod_logs = find_mod_log_channel(interaction.guild)
            if mod_logs:
                await mod_logs.send(embed=embed)

        except Exception as e:
            await self.handle_error(interaction, e)

    # --- Punishment Removal Helpers & Commands ---
    @app_commands.command(name="cancel-timeout", description="Cancels an active timeout for a user.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def cancel_timeout(self, interaction: discord.Interaction, member: discord.Member):
        if not member.is_timed_out():
            return await interaction.response.send_message(f"{member.mention} is not timed out!", ephemeral=True)
        try:
            await member.edit(timed_out_until=None)
            await interaction.response.send_message(f"Cancelled {member.mention}'s timeout!")
        except Exception as e:
            await self.handle_error(interaction, e)

    async def _remove_punishment_item(self, interaction: discord.Interaction, member: discord.Member, category: str, index: int, label: str):
        try:
            data = load_db()
            gid = str(interaction.guild.id)
            uid = str(member.id)

            if gid not in data or uid not in data[gid] or not data[gid][uid]["punishments"][category]:
                return await interaction.response.send_message(f"{member.mention} has no {label}s recorded!", ephemeral=True)

            p_list = data[gid][uid]["punishments"][category]
            if index < 1 or index > len(p_list):
                return await interaction.response.send_message(f"Invalid {label} number! Choose between 1 and {len(p_list)}.", ephemeral=True)

            p_list.pop(index - 1)
            data[gid][uid]["info"]["punished"] = check_punishments(data[gid][uid])
            save_db(data)

            msg = f"Removed {label} #{index} from {member.mention}'s punishment history!"
            await interaction.response.send_message(msg)

            mod_logs = find_mod_log_channel(interaction.guild)
            if mod_logs:
                await mod_logs.send(msg)

        except Exception as e:
            await self.handle_error(interaction, e)

    @app_commands.command(name="remove-warn", description="Removes a warning from a user's punishment history.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_warn(self, interaction: discord.Interaction, member: discord.Member, warn: int):
        await self._remove_punishment_item(interaction, member, "warns", warn, "warn")

    @app_commands.command(name="remove-timeout", description="Removes a timeout entry from a user's punishment history.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_timeout(self, interaction: discord.Interaction, member: discord.Member, timeout: int):
        await self._remove_punishment_item(interaction, member, "timeouts", timeout, "timeout")

    @app_commands.command(name="remove-ban", description="Removes a ban entry from a user's punishment history.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_ban(self, interaction: discord.Interaction, member: discord.Member, ban: int):
        await self._remove_punishment_item(interaction, member, "bans", ban, "ban")

    # --- View & Edit Commands ---
    @app_commands.command(name="punishments", description="View a user's punishment history in this server.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def punishments(self, interaction: discord.Interaction, member: discord.Member):
        try:
            data = load_db()
            gid = str(interaction.guild.id)
            uid = str(member.id)

            if gid not in data or uid not in data[gid] or not check_punishments(data[gid][uid]):
                return await interaction.response.send_message(f"{member.mention} has no punishments on record in this server!", ephemeral=True)

            record = data[gid][uid]["punishments"]
            embed = discord.Embed(title=f"{member.name}'s Punishments", color=discord.Color.blue())

            for idx, w in enumerate(record.get("warns", []), 1):
                embed.add_field(name=f"Warn #{idx}", value=f"**Reason:** {w['reason']}\n**Staff:** <@{w['staff']}>\n**Date:** {w['date']}", inline=False)
            for idx, t in enumerate(record.get("timeouts", []), 1):
                embed.add_field(name=f"Timeout #{idx}", value=f"**Reason:** {t['reason']}\n**Staff:** <@{t['staff']}>\n**Date:** {t['date']}\n**Duration:** {t['duration']}", inline=False)
            for idx, b in enumerate(record.get("bans", []), 1):
                embed.add_field(name=f"Ban #{idx}", value=f"**Reason:** {b['reason']}\n**Staff:** <@{b['staff']}>\n**Date:** {b['date']}", inline=False)
            for idx, n in enumerate(record.get("notes", []), 1):
                embed.add_field(name=f"Note #{idx}", value=f"**Note:** {n['note']}\n**Staff:** <@{n['staff']}>\n**Date:** {n['date']}", inline=False)

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await self.handle_error(interaction, e)

    @app_commands.command(name="fix-punishment", description="Edits the reason for a recorded punishment.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.choices(type=[
        app_commands.Choice(name='Warn', value='warns'),
        app_commands.Choice(name='Timeout', value='timeouts'),
        app_commands.Choice(name='Ban', value='bans'),
    ])
    async def fix_punishment(self, interaction: discord.Interaction, member: discord.Member, type: app_commands.Choice[str], punishment: int, reason: str):
        try:
            data = load_db()
            gid = str(interaction.guild.id)
            uid = str(member.id)
            category = type.value

            if gid not in data or uid not in data[gid] or not data[gid][uid]["punishments"].get(category):
                return await interaction.response.send_message(f"{member.mention} has no {type.name.lower()}s recorded!", ephemeral=True)

            p_list = data[gid][uid]["punishments"][category]
            if punishment < 1 or punishment > len(p_list):
                return await interaction.response.send_message(f"Invalid number! Choose between 1 and {len(p_list)}.", ephemeral=True)

            p_list[punishment - 1]["reason"] = reason
            save_db(data)

            await interaction.response.send_message(f"Updated {type.name.lower()} #{punishment} for {member.mention}!\nNew Reason: `{reason}`")

        except Exception as e:
            await self.handle_error(interaction, e)

    # --- Notes Commands ---
    @app_commands.command(name="set-note", description="Adds a staff note to a user's profile.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def set_note(self, interaction: discord.Interaction, member: discord.Member, note: str):
        try:
            time_fmt, _ = get_timestamps()
            data = load_db()
            record = get_user_record(data, interaction.guild.id, member.id)

            record["punishments"]["notes"].append({
                "date": time_fmt,
                "staff": str(interaction.user.id),
                "note": note
            })
            save_db(data)

            await interaction.response.send_message(f"Set a note for {member.mention}!")

            mod_logs = find_mod_log_channel(interaction.guild)
            if mod_logs:
                await mod_logs.send(f"Set a note for {member.mention}!")

        except Exception as e:
            await self.handle_error(interaction, e)

    @app_commands.command(name="remove-note", description="Removes a staff note from a user's profile.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_note(self, interaction: discord.Interaction, member: discord.Member, note: int):
        await self._remove_punishment_item(interaction, member, "notes", note, "note")

    # --- Purge & Help ---
    @app_commands.command(name="purge", description="Purges messages from the channel.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int, member: discord.Member = None):
        try:
            await interaction.response.defer(ephemeral=True)
            if member is None:
                deleted = await interaction.channel.purge(limit=amount)
                await interaction.followup.send(f"Purged {len(deleted)} messages!", ephemeral=True)
            else:
                deleted = await interaction.channel.purge(limit=amount, check=lambda m: m.author == member)
                await interaction.followup.send(f"Purged {len(deleted)} messages from {member.mention}!", ephemeral=True)
        except Exception as e:
            await self.handle_error(interaction, e)

    @app_commands.command(name="staff-help", description="Shows the staff help menu.")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.choices(role=[
        app_commands.Choice(name="Moderator", value="moderator"),
        app_commands.Choice(name="Administrator", value="administrator"),
    ])
    async def staff_help(self, interaction: discord.Interaction, role: app_commands.Choice[str]):
        try:
            r = role.value
            perms = interaction.user.guild_permissions

            if r == "moderator" and perms.moderate_members:
                embed = discord.Embed(title="Moderator Help Menu", description="Commands for Moderators:\n\n<> = Required | () = Optional", color=discord.Color.blue())
                embed.add_field(name="`/warn <member> <reason> (evidence)`", value="Warns a member.", inline=False)
                embed.add_field(name="`/timeout <member> <duration> <reason> (evidence)`", value="Times out a member.", inline=False)
                embed.add_field(name="`/ban <member> <reason> (evidence)`", value="Bans a member.", inline=False)
                embed.add_field(name="`/set-note <member> <note>`", value="Adds a note to a member's profile.", inline=False)
                embed.add_field(name="`/purge <amount> (member)`", value="Purges messages in the channel.", inline=False)
                embed.add_field(name="`/punishments <member>`", value="Shows punishment history.", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)

            elif r == "administrator" and perms.administrator:
                embed = discord.Embed(title="Administrator Help Menu", description="Commands for Administrators:\n\n<> = Required | () = Optional", color=discord.Color.blue())
                embed.add_field(name="`/remove-warn <member> <number>`", value="Removes a warning.", inline=False)
                embed.add_field(name="`/remove-timeout <member> <number>`", value="Removes a timeout entry.", inline=False)
                embed.add_field(name="`/remove-ban <member> <number>`", value="Removes a ban entry.", inline=False)
                embed.add_field(name="`/remove-note <member> <number>`", value="Removes a note.", inline=False)
                embed.add_field(name="`/cancel-timeout <member>`", value="Cancels an active timeout.", inline=False)
                embed.add_field(name="`/fix-punishment <member> <type> <number> <reason>`", value="Edits a punishment reason.", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)

            else:
                await interaction.response.send_message("You do not have the permissions required to view that help menu!", ephemeral=True)

        except Exception as e:
            await self.handle_error(interaction, e)


async def setup(bot):
    await bot.add_cog(Moderation(bot))