# cogs/server_management.py

import discord
from discord.ext import commands
from discord import app_commands
import os


class ServerManagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_settings = bot.guild_settings

    # ========== on_member_join (welcome) ==========
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id_str = str(member.guild.id)
        settings = self.guild_settings.find_one({"guildId": guild_id_str})
        if not settings:
            return

        # Welcome channel
        channel_id = settings.get("welcome_channel_id")
        if channel_id:
            channel = member.guild.get_channel(int(channel_id))
            if channel:
                welcome_msg = settings.get("messageOnMemberJoin", "Welcome to our server, {user}!")
                formatted_message = welcome_msg.replace("{user}", member.mention)
                await channel.send(formatted_message)

        # Assign roles on join
        role_ids = settings.get("welcomeRole", [])
        for rid in role_ids:
            role_obj = member.guild.get_role(int(rid))
            if role_obj:
                await member.add_roles(role_obj)

    # ========== /createchannel ==========
    @app_commands.command(name="createchannel", description="Create a new text or voice channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def createchannel(self, interaction: discord.Interaction, name: str, channel_type: str):
        if channel_type.lower() == "text":
            await interaction.guild.create_text_channel(name=name)
        elif channel_type.lower() == "voice":
            await interaction.guild.create_voice_channel(name=name)
        else:
            await interaction.response.send_message("Invalid channel type! Use 'text' or 'voice'.", ephemeral=True)
            return
        await interaction.response.send_message(f"{channel_type.capitalize()} channel '{name}' created.")

    # ========== /deleterole ==========
    @app_commands.command(name="deleterole", description="Delete a role from the server")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def deleterole(self, interaction: discord.Interaction, role: discord.Role):
        await role.delete(reason=f"Requested by {interaction.user}")
        await interaction.response.send_message(f"Role '{role.name}' has been deleted.")

    # ========== /createrole ==========
    @app_commands.command(name="createrole", description="Create a new role")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def createrole(self, interaction: discord.Interaction, name: str, color: str = "#FFFFFF"):
        try:
            discord_color = discord.Color(int(color.strip("#"), 16))
            new_role = await interaction.guild.create_role(name=name, color=discord_color)
            await interaction.response.send_message(f"Role '{new_role.name}' created with color {color}.")
        except ValueError:
            await interaction.response.send_message("Invalid color format! Use a hex color code (e.g., #FF5733).", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerManagement(bot))
