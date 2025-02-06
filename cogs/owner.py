# cogs/owner.py

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os

def owner_only():
    async def predicate(ctx_or_interaction):
        owner_id_str = os.getenv("OWNER_ID")
        try:
            owner_id = int(owner_id_str)
        except (TypeError, ValueError):
            # If OWNER_ID is not set correctly, deny access.
            return False
        if isinstance(ctx_or_interaction, commands.Context):
            return ctx_or_interaction.author.id == owner_id
        else:
            return ctx_or_interaction.user.id == owner_id
    return commands.check(predicate)

class Owner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Optional: Set attributes if available on your bot instance.
        self.logger = getattr(bot, "logger", None)
        self.guild_settings = getattr(bot, "guild_settings", None)
        self.remote_config = getattr(bot, "remote_config", None)

    # ========== Owner-Only Slash Command: /broadcast_update ==========
    @app_commands.command(name="broadcast_update", description="Broadcast an update to all servers (slash command).")
    @owner_only()
    async def broadcast_update_slash(self, interaction: discord.Interaction, update_message: str):
        await interaction.response.defer(thinking=True)
        success_count = 0
        failed_guilds = []

        for guild in self.bot.guilds:
            settings = self.guild_settings.find_one({"guildId": str(guild.id)}) if self.guild_settings else None
            if settings and "logChannel" in settings:
                log_channel = guild.get_channel(int(settings["logChannel"]))
                if log_channel:
                    try:
                        await log_channel.send(f"**Developer Announcement:** {update_message}")
                        success_count += 1
                    except Exception as e:
                        if self.logger:
                            self.logger.error(f"Failed to send update to {guild.name}: {e}")
                        failed_guilds.append(guild.name)

        response_message = (
            f"Update broadcasted to {success_count} server(s).\n"
            + (f"Failed for: {', '.join(failed_guilds)}" if failed_guilds else "")
        )
        await interaction.followup.send(response_message, ephemeral=True)

    # ========== Owner-Only Prefix Command: eval ==========
    @commands.command(name="eval", help="Evaluate Python code (Owner Only).")
    @owner_only()
    async def eval_command(self, ctx, *, code):
        try:
            result = eval(code)
            if asyncio.iscoroutine(result):
                result = await result
            await ctx.send(f"Result: {result}")
        except Exception as e:
            await ctx.send(f"Error: {e}")

    # ========== Owner-Only Slash Command: /sync ==========
    @app_commands.command(name="sync", description="Sync slash commands globally or to a specific guild (Owner Only).")
    @owner_only()
    async def sync(self, interaction: discord.Interaction, guild_id: int = None):
        try:
            if guild_id:
                guild = discord.Object(id=guild_id)
                await self.bot.tree.sync(guild=guild)
                await interaction.response.send_message(f"Slash commands synced to guild {guild_id}.", ephemeral=True)
            else:
                await self.bot.tree.sync()
                await interaction.response.send_message("Slash commands synced globally.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error syncing commands: {e}", ephemeral=True)

    # ========== Owner-Only Prefix Command: setconfig ==========
    @commands.command(name="setconfig", help="Set a remote config key-value pair (Owner Only).")
    @owner_only()
    async def set_config(self, ctx, key: str, value: str):
        if self.remote_config:
            self.remote_config.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)
            await ctx.send(f"Configuration {key} has been set to {value}.")
        else:
            await ctx.send("Remote config is not set up.")

    # ========== Owner-Only Prefix Command: getconfig ==========
    @commands.command(name="getconfig", help="Get a remote configuration value by key (Owner Only).")
    @owner_only()
    async def get_config(self, ctx, key: str):
        if self.remote_config:
            config = self.remote_config.find_one({"key": key})
            if config:
                await ctx.send(f"Configuration {key}: {config['value']}.")
            else:
                await ctx.send(f"No configuration found for key {key}.")
        else:
            await ctx.send("Remote config is not set up.")

    # ========== Public Slash Command: /team ==========
    @app_commands.command(name="team", description="Show the X-Ample Development team information.")
    async def team(self, interaction: discord.Interaction):
        # Create a header embed for the team
        header_embed = discord.Embed(
            title="X-Ample Development Team",
            description="Meet our amazing team members below!",
            color=0x1abc9c
        )
        header_embed.set_thumbnail(url="https://i.imgur.com/4bSGPHi.png")
        header_embed.set_footer(text="https://discord.gg/xampledev")

        # Define your team members with their details and image URLs.
        team_members = [
            {
                "name": "Danny",
                "role": "Lead Developer & Founder",
                "image": "https://i.imgur.com/h5tXyyC.png"
            },
            {
                "name": "Timothy",
                "role": "Cyber Security Analyst",
                "image": "https://i.imgur.com/OQznx6h.png"
            },
            {
                "name": "Open Vacancy",
                "role": "Customer Support",
                "image": "https://i.imgur.com/4bSGPHi.png"
            }
            
        ]

        # Create an embed for each team member
        member_embeds = []
        for member in team_members:
            member_embed = discord.Embed(
                title=member["name"],
                description=f"**Role:** {member['role']}",
                color=0x3498db
            )
            member_embed.set_image(url=member["image"])
            member_embed.set_footer(text="X-Ample Development")
            member_embeds.append(member_embed)

        # Send the header embed along with each team member embed as a list.
        embeds = [header_embed] + member_embeds
        await interaction.response.send_message(embeds=embeds)

async def setup(bot: commands.Bot):
    await bot.add_cog(Owner(bot))
