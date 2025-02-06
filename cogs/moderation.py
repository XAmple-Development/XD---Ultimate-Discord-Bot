# cogs/moderation.py

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import os
import logging
import re


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = bot.logger
        self.guild_settings = bot.guild_settings
        self.moderation_logs = bot.moderation_logs
        self.muted_users = {}  # {user_id: [role_ids]}

    # ========== /warn ==========
    @app_commands.command(name="warn", description="Warn a user")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided."):
        guild_id_str = str(interaction.guild.id)
        log_entry = {
            "type": "warning",
            "guildId": guild_id_str,
            "userId": str(user.id),
            "moderatorId": str(interaction.user.id),
            "timestamp": datetime.utcnow(),
            "reason": reason
        }
        self.moderation_logs.insert_one(log_entry)

        warning_count = self.moderation_logs.count_documents({
            "guildId": guild_id_str, 
            "userId": str(user.id), 
            "type": "warning"
        })

        await interaction.response.send_message(
            f"{user.mention} has been warned. Total warnings: {warning_count}."
        )
        await self.send_moderation_log(interaction, f"**{interaction.user}** warned **{user}**. Reason: {reason}. Total warnings: {warning_count}.")

    # Helper to send messages to log channel
    async def send_moderation_log(self, interaction: discord.Interaction, message: str):
        guild_id_str = str(interaction.guild.id)
        guild_settings_data = self.guild_settings.find_one({"guildId": guild_id_str})
        if guild_settings_data and "logChannel" in guild_settings_data:
            log_channel_id = int(guild_settings_data["logChannel"])
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(message)

    # ========== /timeout (prefix command) ==========
    @app_commands.command(name="timeout", description="Timeout a user temporarily.")
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: int, *, reason: str = "No reason provided."):
        """Temporarily timeout a user by <duration> minutes."""
        try:
            timeout_until = discord.utils.utcnow() + timedelta(minutes=duration)
            await member.timeout(until=timeout_until, reason=reason)
            await ctx.send(f"{member.mention} has been timed out for {duration} minutes. Reason: {reason}")
        except discord.Forbidden:
            await ctx.send("I don't have permission to timeout this user.")
        except Exception as e:
            self.logger.error(f"Error timing out {member}: {e}")
            await ctx.send("An error occurred while timing out the user.")

    ### 🔨 **Kick Command**
    @app_commands.command(name="kick", description="Kick multiple users from the server.")
    @app_commands.describe(
        members="Mention the members you want to kick, separated by commas.",
        reason="Provide a reason for kicking the members."
    )
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        members: str,
        reason: Optional[str] = "No reason provided."
    ):
        """
        Kicks multiple members from the server.
        """
        # Parse member mentions or IDs
        member_ids = self.extract_member_ids(members)
        if not member_ids:
            await interaction.response.send_message("❌ No valid member mentions or IDs found.", ephemeral=True)
            return

        success_messages = []
        failure_messages = []

        for member_id in member_ids:
            member = interaction.guild.get_member(member_id)
            if not member:
                failure_messages.append(f"⚠️ Member with ID `{member_id}` not found.")
                continue
            try:
                await member.kick(reason=f"{reason} | Kicked by {interaction.user}")
                success_messages.append(f"✅ Kicked {member.mention}.")
            except discord.Forbidden:
                failure_messages.append(f"⚠️ Failed to kick {member.mention}. Insufficient permissions.")
            except Exception as e:
                self.logger.error(f"Error kicking {member}: {e}")
                failure_messages.append(f"⚠️ Error kicking {member.mention}.")

        # Compile response
        response = ""
        if success_messages:
            response += "\n".join(success_messages)
        if failure_messages:
            response += "\n".join(failure_messages)

        await interaction.response.send_message(response if response else "No actions were performed.", ephemeral=True)

    ### 🛡️ **Ban Command**
    @app_commands.command(name="ban", description="Ban multiple users from the server.")
    @app_commands.describe(
        members="Mention the members you want to ban, separated by commas.",
        reason="Provide a reason for banning the members."
    )
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        members: str,
        reason: Optional[str] = "No reason provided."
    ):
        """
        Bans multiple members from the server.
        """
        # Parse member mentions or IDs
        member_ids = self.extract_member_ids(members)
        if not member_ids:
            await interaction.response.send_message("❌ No valid member mentions or IDs found.", ephemeral=True)
            return

        success_messages = []
        failure_messages = []

        for member_id in member_ids:
            member = interaction.guild.get_member(member_id)
            if not member:
                failure_messages.append(f"⚠️ Member with ID `{member_id}` not found.")
                continue
            try:
                await member.ban(reason=f"{reason} | Banned by {interaction.user}")
                success_messages.append(f"✅ Banned {member.mention}.")
            except discord.Forbidden:
                failure_messages.append(f"⚠️ Failed to ban {member.mention}. Insufficient permissions.")
            except Exception as e:
                self.logger.error(f"Error banning {member}: {e}")
                failure_messages.append(f"⚠️ Error banning {member.mention}.")

        # Compile response
        response = ""
        if success_messages:
            response += "\n".join(success_messages)
        if failure_messages:
            response += "\n".join(failure_messages)

        await interaction.response.send_message(response if response else "No actions were performed.", ephemeral=True)

    ### 🚫 **Error Handling**
    @kick.error
    @ban.error
    async def moderation_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You don't have the required permissions to use this command.", ephemeral=True)
        elif isinstance(error, app_commands.MissingRequiredArgument):
            await interaction.response.send_message("❌ Missing required arguments. Please provide all necessary information.", ephemeral=True)
        else:
            self.logger.error(f"Unexpected error in moderation commands: {error}")
            await interaction.response.send_message("❌ An unexpected error occurred. Please try again later.", ephemeral=True)

    ### 🛠️ **Helper Method to Extract Member IDs**
    def extract_member_ids(self, members_str: str) -> list:
        """
        Extracts member IDs from a string containing mentions or plain IDs separated by commas.
        """
        member_ids = []
        # Regular expression to match mentions or plain IDs
        mention_pattern = re.compile(r'<@!?(\d+)>')
        id_pattern = re.compile(r'\b\d{17,19}\b')  # Discord IDs are typically 17-19 digits

        # Split the string by commas
        parts = members_str.split(',')

        for part in parts:
            part = part.strip()
            if match := mention_pattern.match(part):
                member_id = int(match.group(1))
                member_ids.append(member_id)
            elif match := id_pattern.match(part):
                member_id = int(match.group(0))
                member_ids.append(member_id)
            else:
                continue  # Invalid format, skip

        return member_ids

    # ========== /mute ==========
    @app_commands.command(name="mute", description="Mute a user")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def mute(self, interaction: discord.Interaction, user: discord.Member):
        guild_id_str = str(interaction.guild.id)
        moderation_settings = self.guild_settings.find_one({"guildId": guild_id_str})

        if moderation_settings and "mute_role" in moderation_settings:
            mute_role_id = moderation_settings["mute_role"]
            mute_role = interaction.guild.get_role(int(mute_role_id))
            if mute_role:
                # Save current roles except @everyone
                self.muted_users[user.id] = [r.id for r in user.roles[1:]]  
                # Remove them all
                await user.remove_roles(*user.roles[1:], reason="Muted")
                # Add the mute role
                await user.add_roles(mute_role, reason=f"Muted by {interaction.user}")
                await interaction.response.send_message(f"{user.mention} has been muted.")
            else:
                await interaction.response.send_message("Mute role not found.", ephemeral=True)
        else:
            await interaction.response.send_message("Mute role not configured.", ephemeral=True)

    # ========== /unmute ==========
    @app_commands.command(name="unmute", description="Unmute a user")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def unmute(self, interaction: discord.Interaction, user: discord.Member):
        guild_id_str = str(interaction.guild.id)
        moderation_settings = self.guild_settings.find_one({"guildId": guild_id_str})

        if moderation_settings and "mute_role" in moderation_settings:
            mute_role_id = moderation_settings["mute_role"]
            mute_role = interaction.guild.get_role(int(mute_role_id))

            if mute_role in user.roles:
                await user.remove_roles(mute_role, reason="Unmuted")
                if user.id in self.muted_users:
                    roles_to_restore = []
                    for rid in self.muted_users[user.id]:
                        role_obj = interaction.guild.get_role(rid)
                        if role_obj:
                            roles_to_restore.append(role_obj)
                    if roles_to_restore:
                        await user.add_roles(*roles_to_restore, reason="Restored roles after unmute")
                    del self.muted_users[user.id]
                    await interaction.response.send_message(f"{user.mention} has been unmuted and roles restored.")
                else:
                    await interaction.response.send_message(f"{user.mention} was unmuted but had no stored roles.")
            else:
                await interaction.response.send_message(f"{user.mention} is not muted.")
        else:
            await interaction.response.send_message("Mute role not configured.", ephemeral=True)

    # ========== /purge ==========
    @app_commands.command(name="purge", description="Purge messages")
    @app_commands.checks.has_permissions(manage_messages=True)
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def purge(self, interaction: discord.Interaction, amount: int):
        await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"Purged {amount} messages.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
