# cogs/automod.py

import discord
from discord.ext import commands
import time
import re
from collections import defaultdict
import os


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = bot.logger
        self.guild_settings = bot.guild_settings

        # In-memory message timestamps: {guild_id: {user_id: [timestamps]}}
        self.user_message_history = defaultdict(lambda: defaultdict(list))

        # Fallback defaults if not found in DB
        self.default_spam_limit = 5
        self.default_time_window = 10
        self.default_banned_words = ["cunt", "slag"]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        guild_id_str = str(message.guild.id)
        # Retrieve custom auto-mod settings from DB
        guild_data = self.guild_settings.find_one({"guildId": guild_id_str}) or {}
        spam_limit = guild_data.get("spam_limit", self.default_spam_limit)
        time_window = guild_data.get("time_window", self.default_time_window)
        banned_words = guild_data.get("banned_words", self.default_banned_words)

        # Optional: only run if guild is premium? If so, uncomment below:
        # if message.guild.id not in self.bot.premium_guilds:
        #     return

        # ====== Spam Check ======
        now = time.time()
        self.user_message_history[guild_id_str][message.author.id].append(now)
        # Remove timestamps older than `time_window` seconds
        self.user_message_history[guild_id_str][message.author.id] = [
            t for t in self.user_message_history[guild_id_str][message.author.id]
            if now - t <= time_window
        ]
        if len(self.user_message_history[guild_id_str][message.author.id]) > spam_limit:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, please stop spamming!")
            await self.log_moderation_action(message.guild, "Spam Detected", f"User {message.author} exceeded spam limit.")
            return

        # ====== Banned Words Check ======
        for bw in banned_words:
            if re.search(rf"\b{bw}\b", message.content, re.IGNORECASE):
                await message.delete()
                await message.channel.send(f"{message.author.mention}, that word is not allowed!")
                await self.log_moderation_action(message.guild, "Banned Word Detected", f"User {message.author} used banned word: {bw}.")
                return

        # Allow other commands to process
        await self.bot.process_commands(message)

    async def log_moderation_action(self, guild: discord.Guild, action: str, details: str):
        guild_data = self.guild_settings.find_one({"guildId": str(guild.id)})
        if guild_data and "logChannel" in guild_data:
            log_channel_id = int(guild_data["logChannel"])
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(title="Auto-Moderation Action", color=discord.Color.orange())
                embed.add_field(name="Action", value=action, inline=False)
                embed.add_field(name="Details", value=details, inline=False)
                await log_channel.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
