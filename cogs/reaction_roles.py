import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

class ReactionRoles(commands.Cog):
    """
    Simple Reaction Role system using slash commands and raw reaction events.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db  # Reference your MongoDB or other database
        # We'll store records in a collection named 'reactionRoles'
        self.reaction_col = self.db.reactionRoles

    # ------------------------------------------
    # Slash Command Group: /reactionrole ...
    # ------------------------------------------
    @app_commands.command(name="addreactionrole", description="Link an emoji reaction to a role on an existing message.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add_reaction_role(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: str,
        emoji: str,
        role: discord.Role
    ):
        """
        /addreactionrole #channel <message_id> :emoji: @Role
        This will create a record so that when someone reacts with <emoji> on <message_id>,
        they get <role>.
        """
        # 1) Check if the message exists
        try:
            msg_id_int = int(message_id)
            target_message = await channel.fetch_message(msg_id_int)
        except (ValueError, discord.NotFound):
            await interaction.response.send_message(
                f"Could not find message with ID `{message_id}` in {channel.mention}.",
                ephemeral=True
            )
            return

        # 2) Insert into DB
        doc = {
            "guildId": str(interaction.guild_id),
            "channelId": str(channel.id),
            "messageId": str(message_id),
            "emoji": emoji,
            "roleId": str(role.id),
            "action": "toggle"  # or something else if you want different logic
        }
        self.reaction_col.insert_one(doc)

        # 3) Optionally add the reaction to the message
        try:
            await target_message.add_reaction(emoji)
        except discord.HTTPException:
            # If the bot can't add this reaction (invalid emoji, etc.), it won't fail the command
            pass

        await interaction.response.send_message(
            f"Reaction role set: React with {emoji} on [this message]({target_message.jump_url}) "
            f"to get/remove the {role.mention} role.",
            ephemeral=True
        )

    @app_commands.command(name="removereactionrole", description="Remove a reaction-to-role link.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove_reaction_role(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str
    ):
        """
        /removereactionrole <message_id> :emoji:
        Removes any DB record linking this emoji to a role for that message.
        """
        result = self.reaction_col.delete_one({
            "guildId": str(interaction.guild_id),
            "messageId": message_id,
            "emoji": emoji
        })

        if result.deleted_count > 0:
            await interaction.response.send_message(
                f"Removed reaction role for emoji {emoji} on message `{message_id}`.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"No reaction role found for {emoji} on message `{message_id}`.",
                ephemeral=True
            )

    @app_commands.command(name="listreactionroles", description="List all reaction-role links in this server.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def list_reaction_roles(self, interaction: discord.Interaction):
        """
        /listreactionroles
        Displays all stored reaction-role entries for the current guild.
        """
        cursor = self.reaction_col.find({"guildId": str(interaction.guild_id)})
        entries = list(cursor)
        if not entries:
            await interaction.response.send_message("No reaction roles found for this server.", ephemeral=True)
            return

        description_lines = []
        for doc in entries:
            description_lines.append(
                f"- **Message:** {doc['messageId']}, **Emoji:** {doc['emoji']}, **Role:** <@&{doc['roleId']}>"
            )
        embed = discord.Embed(
            title="Reaction Roles",
            description="\n".join(description_lines),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------
    # Events: on_raw_reaction_add / remove
    # ------------------------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        Triggered whenever a reaction is added to a message, including older messages.
        We'll check if it's one of our stored reaction roles, then assign the role.
        """
        # 1) Ignore bots
        if payload.member is None or payload.member.bot:
            return

        # 2) Check DB for a matching record
        doc = self.reaction_col.find_one({
            "guildId": str(payload.guild_id),
            "channelId": str(payload.channel_id),
            "messageId": str(payload.message_id),
            "emoji": str(payload.emoji)  # using the exact string of the emoji
        })

        if not doc:
            return  # Not a reaction role we're tracking

        # 3) Assign the role
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role = guild.get_role(int(doc["roleId"]))
        if role is None:
            return

        try:
            await payload.member.add_roles(role, reason="Reaction role added.")
        except discord.Forbidden:
            # The bot doesn't have permission to assign that role
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """
        Triggered whenever a reaction is removed. We'll remove the role if 'action' is toggle.
        """
        # If we only want the role removed if 'action' is toggle or certain logic, we can do that check
        doc = self.reaction_col.find_one({
            "guildId": str(payload.guild_id),
            "channelId": str(payload.channel_id),
            "messageId": str(payload.message_id),
            "emoji": str(payload.emoji)
        })
        if not doc:
            return

        if doc.get("action") != "toggle":
            return  # Maybe we don't remove roles for other action types

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        role = guild.get_role(int(doc["roleId"]))
        if not role:
            return

        try:
            await member.remove_roles(role, reason="Reaction role removed.")
        except discord.Forbidden:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
