# cogs/utilities.py

import discord
from discord.ext import commands
from discord import app_commands
import os


class Utilities(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = bot.logger
        self.guild_settings = bot.guild_settings
        self.updates_collection = bot.db.updates  # If you store updates in db.updates

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = self.bot.latency * 1000
        await interaction.response.send_message(f"Pong! Latency: {latency_ms:.2f}ms.")

    @app_commands.command(name="help", description="List all bot commands")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Help - X-Ample Ultimate Bot", description="List of available commands:", color=discord.Color.green())

        embed.add_field(
            name="Moderation",
            value="/warn, /mute, /unmute, !bulk_action, !timeout, /purge, etc.",
            inline=False
        )
        embed.add_field(
            name="Utilities",
            value="/ping, /help, /update-log, /setupdateschannel, etc.",
            inline=False
        )
        embed.add_field(
            name="Premium",
            value="/rank, /remindme, /poll, /slowmode, /setnickname, /premiumstats, etc.",
            inline=False
        )
        embed.add_field(
            name="Server Management",
            value="/createchannel, /createrole, /deleterole, etc.",
            inline=False
        )
        embed.add_field(
            name="Owner Only",
            value="!broadcast_update, /broadcast_update, !eval, !sync, !setconfig, !getconfig, etc.",
            inline=False
        )

        embed.set_footer(text="X-Ample Development")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setupdateschannel", description="Set the updates channel for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setupdateschannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        guild_id_str = str(interaction.guild.id)
        self.guild_settings.update_one(
            {"guildId": guild_id_str},
            {"$set": {"updates_channel_id": str(channel.id)}},
            upsert=True
        )
        await interaction.response.send_message(f"Updates channel set to {channel.mention}.")

    @app_commands.command(name="update-log", description="View the latest update information.")
    async def update_log(self, interaction: discord.Interaction):
        latest_update = self.updates_collection.find_one(sort=[("release_date", -1)])
        if not latest_update:
            await interaction.response.send_message("No updates found in the database.", ephemeral=True)
            return

        embed = discord.Embed(title=f"📝 Latest Update: v{latest_update['version']}", color=discord.Color.blue())
        embed.add_field(name="Description", value=latest_update["description"], inline=False)
        embed.set_footer(text=f"Released on: {latest_update['release_date']}")

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utilities(bot))
