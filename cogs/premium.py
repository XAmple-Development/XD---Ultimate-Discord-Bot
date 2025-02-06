# cogs/premium.py

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
import re
import os


def premium_required():
    """Check decorator to ensure the command can only run in premium guilds."""
    async def predicate(interaction: discord.Interaction):
        if interaction.guild.id not in interaction.client.premium_guilds:
            await interaction.response.send_message(
                "This feature is only available for premium subscribers. Subscribe to unlock!",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)


class Premium(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = bot.logger
        self.levels = bot.levels  # Mongo collection for XP
        self.guild_settings = bot.guild_settings

    # ----- Leveling on_message (optional if you want to keep it separate) -----
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Example leveling logic, only for premium guilds."""
        if message.author.bot:
            return

        if message.guild.id not in self.bot.premium_guilds:
            return  # Skip if not premium

        # Basic leveling:
        guild_id_str = str(message.guild.id)
        user_id_str = str(message.author.id)
        user_data = self.levels.find_one({"guildId": guild_id_str, "userId": user_id_str})
        if not user_data:
            user_data = {"guildId": guild_id_str, "userId": user_id_str, "xp": 0, "level": 1}
            self.levels.insert_one(user_data)

        xp = user_data.get("xp", 0) + 10
        level = user_data.get("level", 1)

        # Example threshold
        if xp >= 100 * level:
            level += 1
            await message.channel.send(f"{message.author.mention} leveled up to Level {level}!")
        self.levels.update_one(
            {"guildId": guild_id_str, "userId": user_id_str},
            {"$set": {"xp": xp, "level": level}}
        )

    # ----- /rank -----
    @app_commands.command(name="rank", description="Check your rank")
    @premium_required()
    async def rank(self, interaction: discord.Interaction):
        user_id_str = str(interaction.user.id)
        guild_id_str = str(interaction.guild.id)
        user_data = self.levels.find_one({"guildId": guild_id_str, "userId": user_id_str})

        if user_data:
            xp = user_data.get("xp", 0)
            level = user_data.get("level", 1)
            await interaction.response.send_message(f"You are Level {level} with {xp} XP.")
        else:
            await interaction.response.send_message("You don't have any levels yet!")

    # ----- /remindme -----
    @app_commands.command(name="remindme", description="Set a reminder (Premium Only)")
    @premium_required()
    async def remindme(self, interaction: discord.Interaction, time_in_minutes: int, *, reminder_message: str):
        await interaction.response.send_message(
            f"Reminder set! I'll remind you in {time_in_minutes} minute(s).",
            ephemeral=True
        )
        await asyncio.sleep(time_in_minutes * 60)
        await interaction.user.send(f"⏰ Reminder: {reminder_message}")

    # ----- /poll -----
    @app_commands.command(name="poll", description="Create a poll (Premium)")
    @premium_required()
    async def poll(self, interaction: discord.Interaction, question: str, option1: str, option2: str):
        embed = discord.Embed(title="Poll", description=question, color=discord.Color.blurple())
        embed.add_field(name="1️⃣", value=option1, inline=False)
        embed.add_field(name="2️⃣", value=option2, inline=False)
        poll_message = await interaction.channel.send(embed=embed)
        await poll_message.add_reaction("1️⃣")
        await poll_message.add_reaction("2️⃣")
        await interaction.response.send_message("Poll created!", ephemeral=True)

    # ----- /setnickname -----
    @app_commands.command(name="setnickname", description="Set the bot's nickname (Premium)")
    @premium_required()
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def setnickname(self, interaction: discord.Interaction, nickname: str):
        try:
            await interaction.guild.me.edit(nick=nickname)
            await interaction.response.send_message(f"Bot nickname changed to '{nickname}'.")
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to change my nickname.", ephemeral=True)

    # ----- /premiumstats -----
    @app_commands.command(name="premiumstats", description="View detailed premium-only server stats")
    @premium_required()
    async def premiumstats(self, interaction: discord.Interaction):
        guild = interaction.guild
        total_members = guild.member_count
        online_members = sum(1 for m in guild.members if m.status != discord.Status.offline)
        bot_count = sum(1 for m in guild.members if m.bot)
        human_count = total_members - bot_count
        text_channels = len([c for c in guild.channels if isinstance(c, discord.TextChannel)])
        voice_channels = len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])
        total_channels = text_channels + voice_channels

        embed = discord.Embed(title=f"Premium Stats for {guild.name}", color=discord.Color.gold())
        embed.add_field(name="Total Members", value=total_members, inline=True)
        embed.add_field(name="Online Members", value=online_members, inline=True)
        embed.add_field(name="Humans", value=human_count, inline=True)
        embed.add_field(name="Bots", value=bot_count, inline=True)
        embed.add_field(name="Text Channels", value=text_channels, inline=True)
        embed.add_field(name="Voice Channels", value=voice_channels, inline=True)
        embed.add_field(name="Total Channels", value=total_channels, inline=True)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Premium(bot))
