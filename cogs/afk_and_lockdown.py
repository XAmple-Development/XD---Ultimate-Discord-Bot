# cogs/afk_and_lockdown.py

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

class AFKAndLockdown(commands.Cog):
    """
    Implements two main features:
    1) AFK/Busy Status
    2) Lockdown / Slowmode Toggle
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_settings = bot.guild_settings  # Example: your MongoDB collection reference, if needed
        # If you want to store AFK statuses in a DB, do so. Otherwise, use a dict in memory:
        self.afk_users = {}  # {user_id: {"reason": str, "guild_id": int}}

    # ======================================================
    # =============== 1) AFK / Busy Feature ================
    # ======================================================

    @app_commands.command(
        name="afk",
        description="Set your AFK (Away) status with an optional message."
    )
    async def afk(self, interaction: discord.Interaction, reason: Optional[str] = "AFK"):
        """
        /afk [reason]
        Sets the user's AFK status. When someone mentions them, the bot replies with their AFK message.
        When they speak again, AFK status is removed.
        """
        user_id = interaction.user.id
        self.afk_users[user_id] = {
            "reason": reason,
            "guild_id": interaction.guild_id,
        }
        await interaction.response.send_message(
            f"You're now AFK. Reason: {reason}", 
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1) Ignore bot messages
        if message.author.bot:
            return
        
        # ============== AFK LOGIC ==============
        # If the author is currently AFK, remove their AFK status if they type
        if message.author.id in self.afk_users:
            del self.afk_users[message.author.id]
            try:
                await message.channel.send(
                    f"Welcome back, {message.author.mention}! I've removed your AFK status."
                )
            except discord.Forbidden:
                pass

        # If the message mentions any AFK user, let them know that user's AFK reason
        if message.mentions:
            for user in message.mentions:
                if user.bot:
                    continue
                if user.id in self.afk_users:
                    afk_info = self.afk_users[user.id]
                    reason = afk_info.get("reason", "AFK")
                    try:
                        await message.channel.send(
                            f"{user.mention} is currently AFK. Reason: {reason}"
                        )
                    except discord.Forbidden:
                        pass

        # If you have prefix commands and want to allow them after this logic,
        # uncomment the following line:
        # await self.bot.process_commands(message)

    # ======================================================
    # ====== 2) Lockdown / Slowmode Toggle Feature =========
    # ======================================================

    @app_commands.command(
        name="lockdown",
        description="Enable or disable lockdown on a channel. Members with the exempt role can still speak."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lockdown(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        channel: Optional[discord.TextChannel] = None,
        exempt_role: Optional[discord.Role] = None
    ):
        """
        /lockdown <enabled: bool> [channel] [exempt_role]

        If enabled=True, denies @everyone from sending messages.
        But if you provide an exempt_role, that role is allowed to speak.
        If enabled=False, re-allows @everyone to speak.
        Defaults to the current channel if not specified.
        """
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "This command only works on text channels.",
                ephemeral=True
            )
            return

        everyone_role = interaction.guild.default_role  # @everyone
        # Grab or create the @everyone overwrite
        overwrite_everyone = target_channel.overwrites_for(everyone_role)

        if enabled:
            # Lockdown: set @everyone -> send_messages=False
            overwrite_everyone.send_messages = False
            action_text = "LOCKED down"
        else:
            # Unlock: revert @everyone -> send_messages=None (back to default)
            overwrite_everyone.send_messages = None
            action_text = "UNLOCKED"

        # Apply the @everyone overwrite
        try:
            await target_channel.set_permissions(everyone_role, overwrite=overwrite_everyone)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to modify @everyone permissions here.",
                ephemeral=True
            )
            return

        # If we have an exempt role and lockdown is enabled, allow that role to speak
        if exempt_role:
            overwrite_exempt = target_channel.overwrites_for(exempt_role)
            if enabled:
                # Specifically allow them to speak
                overwrite_exempt.send_messages = True
            else:
                # Revert to default
                overwrite_exempt.send_messages = None

            try:
                await target_channel.set_permissions(exempt_role, overwrite=overwrite_exempt)
            except discord.Forbidden:
                await interaction.response.send_message(
                    f"I don't have permission to modify permissions for {exempt_role.mention}.",
                    ephemeral=True
                )
                return

        # Confirmation message
        exempt_msg = f"\nExempt role: {exempt_role.mention}" if exempt_role and enabled else ""
        await interaction.response.send_message(
            f"Channel {target_channel.mention} has been **{action_text}**." + exempt_msg,
            ephemeral=True
        )

    @app_commands.command(
        name="slowmode",
        description="Set slowmode delay (in seconds) for a channel."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(
        self,
        interaction: discord.Interaction,
        delay_in_seconds: int,
        channel: Optional[discord.TextChannel] = None
    ):
        """
        /slowmode <delay_in_seconds> [channel]
        Sets how often users can message. 0 disables slowmode.
        Defaults to the current channel if none specified.
        """
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "This command only works on text channels.",
                ephemeral=True
            )
            return

        # Slowmode limit range from 0 to 21600 sec (6h) in Discord
        if delay_in_seconds < 0 or delay_in_seconds > 21600:
            await interaction.response.send_message(
                "Slowmode delay must be between 0 and 21600 seconds (6 hours).",
                ephemeral=True
            )
            return

        try:
            await target_channel.edit(slowmode_delay=delay_in_seconds)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to set slowmode here.",
                ephemeral=True
            )
            return

        if delay_in_seconds == 0:
            await interaction.response.send_message(
                f"Slowmode disabled in {target_channel.mention}."
            )
        else:
            await interaction.response.send_message(
                f"Slowmode set to **{delay_in_seconds} seconds** in {target_channel.mention}."
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(AFKAndLockdown(bot))
