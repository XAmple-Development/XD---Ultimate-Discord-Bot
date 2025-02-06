# cogs/leaderboard.py

import discord
from discord.ext import commands
from discord import app_commands

class Leaderboard(commands.Cog):
    """
    Cog that provides a /leaderboard command to show top XP earners in the guild.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.levels = bot.levels  # Reference your "levels" MongoDB collection
        self.logger = bot.logger

    @app_commands.command(
        name="leaderboard",
        description="Show the top 10 XP holders in this server."
    )
    async def leaderboard(self, interaction: discord.Interaction):
        """
        Fetch the top 10 users by XP for the current guild and display them.
        """
        guild_id_str = str(interaction.guild.id)
        
        # 1) Fetch top 10 documents
        top_docs = self.levels.find({"guildId": guild_id_str}).sort("xp", -1).limit(10)

        # 2) Build an embed
        embed = discord.Embed(
            title=f"Leaderboard for {interaction.guild.name}",
            description="Top 10 members by XP",
            color=discord.Color.gold()
        )

        # 3) Fill embed with user data
        rank = 1
        for doc in top_docs:
            user_id = doc["userId"]
            xp = doc.get("xp", 0)
            level = doc.get("level", 1)

            try:
                # Try to fetch user from Discord so we can display a name
                user = await self.bot.fetch_user(int(user_id))
                username = user.name
            except Exception:
                # Fallback in case user not found
                username = f"User ID {user_id}"

            embed.add_field(
                name=f"#{rank} — {username}",
                value=f"Level {level} ({xp} XP)",
                inline=False
            )
            rank += 1

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))
