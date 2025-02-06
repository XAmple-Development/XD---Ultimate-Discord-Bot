# main.py

import discord
from discord.ext import commands
from dotenv import load_dotenv
from pymongo import MongoClient
import os
import logging
import asyncio


load_dotenv()

# =============== LOGGING ===============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("my_bot")

# =============== MONGODB SETUP ===============
mongo_uri = os.getenv("MONGODB_URI")
client = MongoClient(mongo_uri)
db = client.get_database(os.getenv("MONGODB_DB_NAME"))

# Example references you might store:
guild_settings = db.guildSettings
moderation_logs = db.moderationLogs
levels = db.levels
error_logs = db.errorLogs
remote_config = db.remoteConfig

# =============== BOT SETUP ===============
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree  # For slash commands

# Optionally store references on the bot so cogs can access them
bot.db = db
bot.logger = logger
bot.guild_settings = guild_settings
bot.moderation_logs = moderation_logs
bot.levels = levels
bot.error_logs = error_logs
bot.remote_config = remote_config

# For your premium logic, store an in-memory set (refreshed by a task):
bot.premium_guilds = set()

# Developer / Owner info
DEV_LOG_CHANNEL_ID = int(os.getenv("DEV_LOG_CHANNEL_ID", 0))
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID", 0))
OWNER_ID = int(os.getenv("OWNER_ID", 0))

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        await tree.sync()
        logger.info("Slash commands synced!")
    except Exception as e:
        logger.error(f"Error syncing slash commands: {e}")

    # You can do other startup logic here
    # e.g., start background tasks, check DB connections, etc.


# Optional: Log all slash command executions to your dev log
@bot.event
async def on_interaction(interaction: discord.Interaction):
    try:
        if interaction.type == discord.InteractionType.application_command:
            dev_guild = bot.get_guild(DEV_GUILD_ID)
            if not dev_guild:
                return

            dev_log_channel = dev_guild.get_channel(DEV_LOG_CHANNEL_ID)
            if not dev_log_channel:
                return

            embed = discord.Embed(title="Slash Command Executed", color=discord.Color.blue())
            embed.add_field(name="Command", value=interaction.command.name if interaction.command else "Unknown", inline=False)
            embed.add_field(name="Executed By", value=f"{interaction.user} ({interaction.user.id})", inline=False)
            embed.add_field(name="Guild", value=f"{interaction.guild.name} ({interaction.guild.id})" if interaction.guild else "DM", inline=False)
            embed.add_field(name="Channel", value=f"{interaction.channel.name} ({interaction.channel.id})" if interaction.channel else "DM", inline=False)
            await dev_log_channel.send(embed=embed)
    except Exception as e:
        logger.error(f"Failed to log slash command interaction: {e}")

# =============== LOAD COGS ===============
INITIAL_EXTENSIONS = [
    "cogs.automod",
    "cogs.moderation",
    "cogs.premium",
    "cogs.server_management",
    "cogs.owner",
    "cogs.utilities",
    "cogs.tasks",
    "cogs.leaderboard",
    "cogs.logging_enhancements",
    "cogs.telephone",
    "cogs.reaction_roles",
    "cogs.afk_and_lockdown"
]

async def main():
    for ext in INITIAL_EXTENSIONS:
        await bot.load_extension(ext)
    await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())

