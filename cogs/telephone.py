import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

def premium_required():
    """Your premium check decorator."""
    async def predicate(interaction: discord.Interaction):
        # For example, if you store premium guilds in bot.premium_guilds
        if interaction.guild.id not in interaction.client.premium_guilds:
            await interaction.response.send_message(
                "This feature is only available for premium subscribers.",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

class GlobalTelephone(commands.Cog):
    """
    One big 'call' bridging across all premium guilds that have a dedicated call channel.

    Flow:
      1) Each premium server sets their call channel via /setcallchannel.
      2) /ring turns bridging ON. All call channels now share messages.
      3) /hangup turns bridging OFF. (Optional).
      4) on_message: if bridging ON and message is in a call channel, forward it to all other call channels.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_settings = bot.guild_settings  # e.g. your MongoDB "guildSettings" collection
        self.bridging = False  # in-memory flag for whether bridging is currently active

    @app_commands.command(name="setcallchannel", description="Set the channel used for global calls in this server.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_call_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        /setcallchannel #some-channel
        This will store the channel ID for cross-server calls (if bridging is ON).
        """
        guild_id_str = str(interaction.guild.id)
        self.guild_settings.update_one(
            {"guildId": guild_id_str},
            {"$set": {"callChannel": str(channel.id)}},
            upsert=True
        )
        await interaction.response.send_message(
            f"Call channel set to {channel.mention} for this server.",
            ephemeral=True
        )

    @app_commands.command(name="ring", description="Start a global call (bridging) with all premium servers' call channels.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ring(self, interaction: discord.Interaction):
        """
        /ring: Immediately starts bridging. 
        Must be run inside the call channel (but we won't strictly require it if you don't want).
        """
        guild_id_str = str(interaction.guild.id)
        # Optional: verify user is actually in the set call channel:
        guild_data = self.guild_settings.find_one({"guildId": guild_id_str}) or {}
        call_channel_id = guild_data.get("callChannel")
        if not call_channel_id:
            await interaction.response.send_message(
                "No call channel set for this server. Use /setcallchannel first.",
                ephemeral=True
            )
            return

        # If you want to require that the user must be in the configured call channel:
        if interaction.channel.id != int(call_channel_id):
            await interaction.response.send_message(
                f"Please run /ring in your configured call channel (<#{call_channel_id}>).",
                ephemeral=True
            )
            return

        if self.bridging:
            await interaction.response.send_message(
                "Global call is already active!",
                ephemeral=True
            )
            return

        # Turn bridging on
        self.bridging = True
        await interaction.response.send_message(
            "☎️ A global call has started! Messages in any configured call channel are now shared among all premium servers.",
            ephemeral=True
        )

        # Notify all other call channels (optional):
        await self._broadcast_message(
            f"☎️ A global call has started by **{interaction.guild.name}**. Messages in any call channel are now linked!"
        )

    @app_commands.command(name="hangup", description="End the global call (bridging).")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def hangup(self, interaction: discord.Interaction):
        """
        /hangup: Turn bridging OFF.
        """
        if not self.bridging:
            await interaction.response.send_message("No active global call to hang up.", ephemeral=True)
            return

        self.bridging = False
        await interaction.response.send_message("☎️ Global call has ended.", ephemeral=True)

        # Notify all other call channels
        await self._broadcast_message(
            f"☎️ The global call has ended. (Hung up by **{interaction.guild.name}**.)"
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        If bridging is ON and this message is in a server's call channel, 
        forward it to all other call channels.
        """
        if message.author.bot or not message.guild:
            return
        if not self.bridging:
            return

        # Check if this guild has a callChannel set and if the message is in it
        guild_data = self.guild_settings.find_one({"guildId": str(message.guild.id)}) or {}
        call_channel_id = guild_data.get("callChannel")
        if not call_channel_id:
            return  # no call channel set

        if message.channel.id != int(call_channel_id):
            return  # user wrote in a different channel

        # Now we broadcast to all other premium servers' call channels
        await self._broadcast_message(
            content=message.content,
            origin_guild=message.guild,
            origin_author=message.author,
            origin_attachments=message.attachments
        )

    async def _broadcast_message(
        self,
        content: str,
        origin_guild: Optional[discord.Guild] = None,
        origin_author: Optional[discord.Member] = None,
        origin_attachments: Optional[list] = None
    ):
        """
        Sends `content` to every premium guild's call channel (except the origin).
        If `origin_guild` is provided, we skip that guild's channel for echo.
        Also tries to forward attachments if provided.
        """
        # Gather all guild settings that have a callChannel
        cursor = self.guild_settings.find({"callChannel": {"$exists": True}})

        # Turn attachments into files if present
        files = []
        if origin_attachments:
            for attach in origin_attachments:
                # Make a File object from each attachment
                files.append(await attach.to_file())

        # Build a prefix, e.g. "[ServerName] Author: ... "
        prefix = ""
        if origin_guild and origin_author:
            prefix = f"**[{origin_guild.name}]** {origin_author.display_name}: "

        # We'll iterate through each guild that has a channel set
        for doc in cursor:
            guild_id = int(doc["guildId"])
            channel_id = int(doc["callChannel"])
            if origin_guild and guild_id == origin_guild.id:
                # skip the origin guild to avoid echo
                continue

            # Attempt to fetch
            guild_obj = self.bot.get_guild(guild_id)
            if not guild_obj:
                continue
            call_ch = guild_obj.get_channel(channel_id)
            if not call_ch:
                continue

            send_content = prefix + (content if content else "")
            # If there's no text but there are attachments, we still want to send them
            if not send_content and files:
                send_content = prefix + "[Attachment]"
            
            try:
                if files:
                    await call_ch.send(send_content, files=files)
                else:
                    if send_content:
                        await call_ch.send(send_content)
            except discord.Forbidden:
                # The bot might not have perms in that channel
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(GlobalTelephone(bot))
