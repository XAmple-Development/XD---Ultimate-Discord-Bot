# cogs/tasks.py

import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone
import aiohttp
import os

class BotTasks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = bot.logger
        self.guild_settings = bot.guild_settings

        # Start tasks
        self.update_server_stats.start()
        self.refresh_premium_guilds.start()

    @tasks.loop(minutes=10)
    async def update_server_stats(self):
        """Periodically update server stats in each guild's stats channel."""
        try:
            total_guilds = len(self.bot.guilds)
            total_users = sum(g.member_count for g in self.bot.guilds)
            premium_count = len(self.bot.premium_guilds)
            latency = self.bot.latency * 1000
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            embed = discord.Embed(title="Live Bot Stats", color=discord.Color.blue())
            embed.add_field(name="Total Guilds", value=total_guilds, inline=True)
            embed.add_field(name="Total Users", value=total_users, inline=True)
            embed.add_field(name="Premium Guilds", value=premium_count, inline=True)
            embed.add_field(name="Latency", value=f"{latency:.2f} ms", inline=True)
            embed.set_footer(text=f"Last updated: {current_time}")

            for guild in self.bot.guilds:
                guild_id_str = str(guild.id)
                guild_data = self.guild_settings.find_one({"guildId": guild_id_str})
                if guild_data and "stats_channel_id" in guild_data:
                    stats_channel_id = int(guild_data["stats_channel_id"])
                    stats_channel = guild.get_channel(stats_channel_id)
                    if stats_channel:
                        # Try to find a recent bot message to edit, else send new
                        edited = False
                        async for msg in stats_channel.history(limit=5):
                            if msg.author == self.bot.user:
                                await msg.edit(embed=embed)
                                edited = True
                                break
                        if not edited:
                            await stats_channel.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Error updating server stats: {e}")

    @tasks.loop(minutes=10)
    async def refresh_premium_guilds(self):
        """Periodically fetch entitlements (premium guilds) from Discord or your DB."""
        self.bot.premium_guilds.clear()
        url = f"https://discord.com/api/v10/applications/{os.getenv('DISCORD_APP_ID')}/entitlements"
        headers = {"Authorization": f"Bot {os.getenv('DISCORD_TOKEN')}"}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        entitlements = await response.json()
                        for ent in entitlements:
                            gid = ent.get("guild_id")
                            if gid:
                                self.bot.premium_guilds.add(int(gid))

                        dev_log_channel_id = int(os.getenv("DEV_LOG_CHANNEL_ID", 0))
                        dev_log_channel = self.bot.get_channel(dev_log_channel_id)
                        if dev_log_channel:
                            await dev_log_channel.send(f"Premium guilds updated: {self.bot.premium_guilds}")
                        self.logger.info(f"Premium guilds updated: {self.bot.premium_guilds}")
                    else:
                        self.logger.error(f"Failed to fetch entitlements. HTTP Status: {response.status}")
            except Exception as e:
                self.logger.error(f"Exception while refreshing premium guilds: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(BotTasks(bot))
