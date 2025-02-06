# cogs/logging_enhancements.py

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

class LoggingEnhancements(commands.Cog):
    """
    Cog to handle enhanced logging: message edits, deletes, member leaves, etc.
    Includes a slash command to toggle each log event per guild.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = bot.logger
        self.guild_settings = bot.guild_settings  # Your "guildSettings" MongoDB collection

    @app_commands.command(
        name="toggle_log_event",
        description="Enable or disable a specific log event (message_edit, message_delete, member_leave)."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_log_event(self, interaction: discord.Interaction, event_name: str, enable: bool):
        """
        Example usage: /toggle_log_event event_name:message_edit enable:true
        """
        guild_id_str = str(interaction.guild.id)

        valid_events = ["message_edit", "message_delete", "member_leave"]
        if event_name not in valid_events:
            await interaction.response.send_message(
                f"Invalid event name. Must be one of {', '.join(valid_events)}.",
                ephemeral=True
            )
            return

        # Fetch or create default
        settings = self.guild_settings.find_one({"guildId": guild_id_str}) or {}
        logging_config = settings.get("logging_events", {})

        # Update the event
        logging_config[event_name] = enable

        # Save back to DB
        self.guild_settings.update_one(
            {"guildId": guild_id_str},
            {"$set": {"logging_events": logging_config}},
            upsert=True
        )

        status = "enabled" if enable else "disabled"
        await interaction.response.send_message(
            f"Logging for **{event_name}** has been {status}.",
            ephemeral=True
        )

    @app_commands.command(name="setlogchannel", description="Set the channel where logs will be posted.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        /setlogchannel #log-channel
        This will store the channel ID in the guild's config for logging.
        """
        self.guild_settings.update_one(
            {"guildId": str(interaction.guild.id)},
            {"$set": {"logChannel": str(channel.id)}},
            upsert=True
        )
        await interaction.response.send_message(f"Log channel set to {channel.mention}", ephemeral=True)

    # ================================================================
    #                   Event Listeners
    # ================================================================
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return  # Skip bot messages / DMs

        guild_id_str = str(before.guild.id)
        settings = self.guild_settings.find_one({"guildId": guild_id_str}) or {}
        logging_config = settings.get("logging_events", {})
        if not logging_config.get("message_edit"):
            return  # This event not enabled

        log_channel_id = settings.get("logChannel")
        if not log_channel_id:
            return

        log_channel = before.guild.get_channel(int(log_channel_id))
        if not log_channel:
            return

        embed = discord.Embed(
            title="Message Edited",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=before.content or "[No content]", inline=False)
        embed.add_field(name="After", value=after.content or "[No content]", inline=False)

        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return  # Skip bots / DMs

        guild_id_str = str(message.guild.id)
        settings = self.guild_settings.find_one({"guildId": guild_id_str}) or {}
        logging_config = settings.get("logging_events", {})
        if not logging_config.get("message_delete"):
            return  # This event not enabled

        log_channel_id = settings.get("logChannel")
        if not log_channel_id:
            return

        log_channel = message.guild.get_channel(int(log_channel_id))
        if not log_channel:
            return

        embed = discord.Embed(
            title="Message Deleted",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Content", value=message.content or "[No content]", inline=False)

        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Fired when a member leaves or is kicked
        guild_id_str = str(member.guild.id)
        settings = self.guild_settings.find_one({"guildId": guild_id_str}) or {}
        logging_config = settings.get("logging_events", {})
        if not logging_config.get("member_leave"):
            return  # This event not enabled

        log_channel_id = settings.get("logChannel")
        if not log_channel_id:
            return

        log_channel = member.guild.get_channel(int(log_channel_id))
        if not log_channel:
            return

        embed = discord.Embed(
            title="Member Left the Server",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        
        await log_channel.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingEnhancements(bot))
