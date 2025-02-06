import discord
from discord import Embed, Color
from discord.ext import tasks, commands
from discord import app_commands
from pymongo import MongoClient
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import asyncio  # Import asyncio module
import aiohttp

# Load environment variables from .env file
load_dotenv()

# Initialize MongoDB client
mongo_uri = os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)
db = client.get_database(os.getenv('MONGODB_DB_NAME'))
guild_settings = db.guildSettings  # Collection name
auto_mod_settings = db.autoMod  # Auto moderation settings collection
moderation_logs = db.moderationLogs  # Collection for storing moderation actions
birthday_collection = db.birthdays
autoMod = db.autoMod

# Initialize bot with intents
intents = discord.Intents.default()
intents.members = True  # Enable member intents
intents.presences = True  # Enable presence intents
intents.message_content = True  # Ensure message content intent is enabled
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Configure sharding
shard_count = 4  # Number of shards
bot = commands.AutoShardedBot(command_prefix='', intents=intents, shard_count=shard_count)

# Function to fetch prefix from MongoDB based on guild ID
async def get_prefix(bot, message):
    # Retrieve guild settings from MongoDB based on guild's guildId
    guild_settings_data = guild_settings.find_one({"guildId": str(message.guild.id)})
    if guild_settings_data:
        prefix_data = guild_settings_data.get('prefixData', '!')
        return prefix_data
    else:
        return '!'  # Default prefix if not found in database

bot.command_prefix = get_prefix  # Set command prefix dynamically

# Initialize user levels dictionary
user_levels = {}

# Event listener for bot initialization
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print(f'discord.py version: {discord.__version__}')
    print(f'Shard ID: {bot.shard_id}')
    print(f'Total Shards: {bot.shard_count}')
    print("Ready!")
    update_server_stats.start()  # Start the server stats update loop
    
start_time = datetime.utcnow()
    
# Command to fetch and display user's avatar
@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author  # If no member is specified, use the command invoker's avatar
    embed = discord.Embed(title=f"{member.display_name}'s Avatar", color=discord.Color.blurple())
    embed.set_image(url=member.avatar_url)
    await ctx.send(embed=embed)
    
# Function to fetch and post stats
async def fetch_and_post_stats():
    total_guilds = len(bot.guilds)
    total_users = sum(guild.member_count for guild in bot.guilds)
    total_channels = sum(len(guild.channels) for guild in bot.guilds)
    shard_id = bot.shard_id if bot.shard_id is not None else "Not Sharded"
    latency = bot.latency * 1000  # Convert to milliseconds

    # Calculate uptime
    current_time = datetime.utcnow()
    uptime = current_time - start_time
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds

    for guild in bot.guilds:
        guild_id = str(guild.id)
        settings = autoMod.find_one({"guildId": guild_id})

        if settings and 'stats_channel_id' in settings:
            stats_channel_id = settings['stats_channel_id']

            if stats_channel_id:
                try:
                    stats_channel = bot.get_channel(int(stats_channel_id))
                except ValueError:
                    print(f"Invalid stats_channel_id '{stats_channel_id}' found for guild ID {guild_id}. Skipping stats update.")
                    continue

                if stats_channel:
                    # Create embed for stats
                    embed = Embed(
                        title="Live Bot Stats - Auto updates every 10 Minutes",
                        color=Color.blue()
                    )
                    embed.add_field(name="Total Guilds", value=total_guilds, inline=True)
                    embed.add_field(name="Total Users in all Guilds", value=total_users, inline=True)
                    embed.add_field(name="Uptime", value=uptime_str, inline=True)
                    embed.add_field(name="Shard ID", value=shard_id, inline=True)
                    embed.add_field(name="Total Shards", value=bot.shard_count, inline=True)
                    embed.add_field(name="Latency", value=f"{latency:.2f} ms", inline=True)
                    embed.set_footer(text="X-Ample Development", icon_url=bot.user.display_avatar.url)

                    # Fetch the last message in the channel to update it
                    async for message in stats_channel.history(limit=1):
                        if message.author == bot.user:
                            try:
                                await message.delete()
                            except discord.Forbidden:
                                print(f"Could not delete message in {stats_channel.name} due to lack of permissions.")
                            break

                    # Post the updated stats embed
                    try:
                        await stats_channel.send(embed=embed)
                    except discord.Forbidden:
                        print(f"Could not send message to {stats_channel.name} due to lack of permissions.")
                    except discord.HTTPException as e:
                        print(f"Failed to send message to {stats_channel.name}. Error: {e}")
                else:
                    print(f"Stats channel with ID {stats_channel_id} not found.")
            else:
                print(f"Stats channel ID not set for guild ID {guild_id}. Skipping stats update.")
        else:
            print(f"Stats channel settings not found for guild ID {guild_id}. Skipping stats update.")

# Task to update server stats periodically
@tasks.loop(minutes=10)
async def update_server_stats():
    await fetch_and_post_stats()

# Command to set the stats channel
@bot.command()
@commands.has_permissions(administrator=True)
async def setstatschannel(ctx, channel: discord.TextChannel):
    guild_id = str(ctx.guild.id)
    autoMod.update_one(
        {"guildId": guild_id},
        {"$set": {"stats_channel_id": str(channel.id)}},
        upsert=True
    )
    await ctx.send(f"Stats channel set to {channel.mention}")

# Command to kick a user
@bot.command()
async def kick(ctx, user: discord.Member, *, reason=None):
    guild_id = str(ctx.guild.id)
    auto_mod_data = auto_mod_settings.find_one({"guildId": guild_id})
    if auto_mod_data:
        admin_role_id = auto_mod_data.get('admin_role')
        kick_message = auto_mod_data.get('kick_message', 'You have been kicked.')
        
        if admin_role_id and discord.utils.get(ctx.author.roles, id=int(admin_role_id)):
            # Log the ban to moderation_logs collection
            log_entry = {
                'type': 'kick',
                'guildId': guild_id,
                'userId': str(user.id),
                'moderatorId': str(ctx.author.id),
                'timestamp': datetime.utcnow(),
                'reason': reason
            }
            moderation_logs.insert_one(log_entry)
            
            # Notify user via DM
            try:
                await user.send(f"{kick_message} Reason: {reason}")
            except discord.Forbidden:
                await ctx.send(f"Failed to send ban DM to {user.mention}. They may have DMs disabled.")
            
            # Ban user
            await ctx.guild.kick(user, reason=reason)
            await ctx.send(f"{user.mention} has been kicked.")
        else:
            await ctx.send("You do not have permission to use this command.")
    else:
        await ctx.send("Auto moderation settings not found.")

# Event listener for when a member joins
@bot.event
async def on_member_join(member):
    try:
        # Retrieve guild settings from MongoDB based on guild's guildId
        guild_settings_data = guild_settings.find_one({"guildId": str(member.guild.id)})
        if guild_settings_data:
            await process_guild_settings(guild_settings_data, member)
        else:
            print(f"No guild settings found for guild ID {member.guild.id}")
    except Exception as e:
        print(f"Failed to fetch or process guild settings. Error: {e}")

# Command to get the latest welcome message from MongoDB based on guild's guildId
@bot.command()
async def welcomemessage(ctx):
    try:
        # Retrieve guild settings from MongoDB based on guild's guildId
        guild_settings_data = guild_settings.find_one({"guildId": str(ctx.guild.id)})
        if guild_settings_data:
            guild_settings_str = guild_settings_data.get('guild_Settings', '')
            welcome_channel_id = guild_settings_data.get('welcome_channel_id', None)
            
            if guild_settings_str:
                await ctx.send(f"Latest welcome message:\n{guild_settings_str}")
            else:
                await ctx.send("No welcome message found for this guild in the database.")
            
            if welcome_channel_id:
                channel = bot.get_channel(int(welcome_channel_id))
                if channel:
                    # Replace {user} with a placeholder since we're sending to channel
                    welcome_message = guild_settings_str.replace("{user}", "@User")
                    await channel.send(welcome_message)
                    await ctx.send(f"Welcome message posted in {channel.mention}")
                else:
                    await ctx.send("Welcome message channel not found.")
            else:
                await ctx.send("No welcome message channel set.")
        else:
            await ctx.send("No welcome message found for this guild in the database. Reach out to support, If you are having issues.")
    except Exception as e:
        await ctx.send(f"Failed to fetch or post welcome message from database. Error: {e}")

# Function to process guild settings from MongoDB
async def process_guild_settings(guild_settings_data, member):
    try:
        guild_settings_str = guild_settings_data.get('guild_Settings', '')
        if guild_settings_str:
            welcome_channel_id = guild_settings_data.get('welcome_channel_id', None)
            if welcome_channel_id:
                channel = bot.get_channel(int(welcome_channel_id))
                if channel:
                    # Replace {user} with member mention and send welcome message
                    welcome_message = guild_settings_str.replace("{user}", member.mention)
                    await channel.send(welcome_message)
                else:
                    print(f"Welcome message channel not found for guild ID {member.guild.id}")
            else:
                print(f"No welcome message channel set for guild ID {member.guild.id}")
        else:
            print(f"No welcome message found for guild ID {member.guild.id}")

        # Assign role to the new member if welcomeRole is set in database
        welcome_role_id = guild_settings_data.get('welcomeRole')
        if welcome_role_id:
            role = member.guild.get_role(int(welcome_role_id))
            if role:
                await member.add_roles(role, reason="Assigned on join")
                print(f"Assigned role {role.name} to {member.display_name}")
            else:
                print(f"Role with ID {welcome_role_id} not found in guild {member.guild.id}")
    except Exception as e:
        print(f"Failed to process guild settings. Error: {e}")

# Command to change bot's prefix
@bot.command()
async def changeprefix(ctx, new_prefix: str):
    guild_id = str(ctx.guild.id)
    try:
        result = guild_settings.update_one(
            {"guildId": guild_id},
            {"$set": {"prefixData": new_prefix}},
            upsert=True
        )
        if result.modified_count > 0 or result.upserted_id:
            await ctx.send(f"Prefix set to: {new_prefix}")
        else:
            await ctx.send("Failed to set prefix.")
    except Exception as e:
        await ctx.send(f"Failed to set prefix. Error: {e}")

# Command to warn a user
@bot.command()
async def warn(ctx, user: discord.Member):
    guild_id = str(ctx.guild.id)
    auto_mod_data = auto_mod_settings.find_one({"guildId": guild_id})
    if auto_mod_data:
        admin_role_id = auto_mod_data.get('admin_role')
        warn_message = auto_mod_data.get('warn_message', 'You have been warned.')
        amount_of_warn = auto_mod_data.get('amount_of_warn', 10)
        
        if admin_role_id and discord.utils.get(ctx.author.roles, id=int(admin_role_id)):
            # Log the warning to moderation_logs collection
            log_entry = {
                'type': 'warning',
                'guildId': guild_id,
                'userId': str(user.id),
                'moderatorId': str(ctx.author.id),
                'timestamp': datetime.utcnow(),
                'message': f'{user.name} warned by {ctx.author.name}'
            }
            moderation_logs.insert_one(log_entry)
            
            # Count warnings
            warning_count = moderation_logs.count_documents({'guildId': guild_id, 'userId': str(user.id), 'type': 'warning'})
            
            # Notify user via DM
            try:
                await user.send(f"You've been warned by {ctx.author.name}")
            except discord.Forbidden:
                await ctx.send(f"Failed to send warning DM to {user.mention}. They may have DMs disabled.")
            
            await ctx.send(f"{user.mention} has been warned. This user has been warned {warning_count} times.")
            
            # Take action if warning threshold is reached
            if warning_count >= int(amount_of_warn):
                await ban(ctx, user, reason="Reached the maximum number of warnings and is now banned.")
        else:
            await ctx.send("You do not have permission to use this command.")
    else:
        await ctx.send("Auto moderation settings not found.")

# Command to ban a user
@bot.command()
async def ban(ctx, user: discord.Member, *, reason=None):
    guild_id = str(ctx.guild.id)
    auto_mod_data = auto_mod_settings.find_one({"guildId": guild_id})
    if auto_mod_data:
        admin_role_id = auto_mod_data.get('admin_role')
        ban_message = auto_mod_data.get('ban_message', 'You have been banned.')
        
        if admin_role_id and discord.utils.get(ctx.author.roles, id=int(admin_role_id)):
            # Log the ban to moderation_logs collection
            log_entry = {
                'type': 'ban',
                'guildId': guild_id,
                'userId': str(user.id),
                'moderatorId': str(ctx.author.id),
                'timestamp': datetime.utcnow(),
                'reason': reason
            }
            moderation_logs.insert_one(log_entry)
            
            # Notify user via DM
            try:
                await user.send(f"{ban_message} Reason: {reason}")
            except discord.Forbidden:
                await ctx.send(f"Failed to send ban DM to {user.mention}. They may have DMs disabled.")
            
            # Ban user
            await ctx.guild.ban(user, reason=reason)
            await ctx.send(f"{user.mention} has been banned.")
        else:
            await ctx.send("You do not have permission to use this command.")
    else:
        await ctx.send("Auto moderation settings not found.")
        
# Command to mute a user
@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, user: discord.Member, duration: int = None):
    guild_id = str(ctx.guild.id)
    auto_mod_data = auto_mod_settings.find_one({"guildId": guild_id})
    if auto_mod_data:
        mute_role_id = auto_mod_data.get('mute_role')
        
        if mute_role_id:
            mute_role = ctx.guild.get_role(int(mute_role_id))
            if mute_role:
                await user.add_roles(mute_role, reason=f"Muted by {ctx.author.name}")
                await ctx.send(f"{user.mention} has been muted.")
                
                # Log the mute to moderation_logs collection
                log_entry = {
                    'type': 'mute',
                    'guildId': guild_id,
                    'userId': str(user.id),
                    'moderatorId': str(ctx.author.id),
                    'timestamp': datetime.utcnow(),
                    'duration': duration if duration else 'Permanent',
                    'reason': f"Muted by {ctx.author.name}"
                }
                moderation_logs.insert_one(log_entry)
                
                if duration:
                    await ctx.send(f"{user.mention} will be unmuted in {duration} minutes.")
                    await asyncio.sleep(duration * 60)
                    await user.remove_roles(mute_role, reason="Mute duration expired")
                    await ctx.send(f"{user.mention} has been unmuted.")
            else:
                await ctx.send("Mute role not found in this server.")
        else:
            await ctx.send("Mute role is not set in the database.")
    else:
        await ctx.send("Auto moderation settings not found.")
    
@bot.command()
async def birthday(ctx, date: str):
    try:
        # Parse the input date
        birthday = datetime.strptime(date, "%d/%m").strftime("%d/%m")
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)
        
        # Store the birthday in the database
        birthday_collection.update_one(
            {'userId': user_id, 'guildId': guild_id},
            {'$set': {'birthday': birthday}},
            upsert=True
        )
        await ctx.send(f"Your birthday has been set to {date}.")
    except ValueError:
        await ctx.send("Invalid date format. Please use DD/MM.")

@tasks.loop(hours=24)
async def check_birthdays():
    today = datetime.utcnow().strftime("%d/%m")
    
    # Check for users with today's birthday
    birthday_users = birthday_collection.find({"birthday": today})
    
    for user_data in birthday_users:
        user_id = user_data['userId']
        guild_id = user_data['guildId']
        
        guild = bot.get_guild(int(guild_id))
        if guild:
            user = guild.get_member(int(user_id))
            if user:
                guild_data = guild_settings.find_one({"guildId": guild_id})
                if guild_data:
                    channel_id = guild_data.get('birthday_channel_id')
                    if channel_id:
                        channel = guild.get_channel(int(channel_id))
                        if channel:
                            await channel.send(f"Happy Birthday {user.mention}!")       
        
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id
    if user_id not in user_levels:
        user_levels[user_id] = {"xp": 0, "level": 1}

    user_levels[user_id]["xp"] += 10  # Increment XP

    xp = user_levels[user_id]["xp"]
    level = user_levels[user_id]["level"]

    if xp >= 100 * level:  # Simple leveling formula
        user_levels[user_id]["level"] += 1
        await message.channel.send(f"{message.author.mention} has leveled up to {level + 1}!")

    await bot.process_commands(message)
    
@bot.command()
async def poll(ctx, *, question):
    embed = discord.Embed(title="Poll", description=question, color=discord.Color.green())
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")
    
@bot.command()
async def info(ctx):
    bot_owner = "X-Ample Development"  # Replace with your Discord username and tag
    support_server_link = "https://discord.gg/xampledev"  # Replace with your support server invite link
    dashboard_link = "https://x-ampledevelopment.com"  # Replace with your dashboard link

    embed = discord.Embed(
        title=f"{bot.user.name} Information",
        color=discord.Color.blue()
    )
    embed.add_field(name="Bot Name", value=bot.user.name, inline=True)
    embed.add_field(name="Current Ping", value=f"{round(bot.latency * 1000)} ms", inline=True)
    embed.add_field(name="Owner", value=bot_owner, inline=True)
    embed.add_field(name="Support Server", value=f"[Join Here]({support_server_link})", inline=True)
    embed.add_field(name="Dashboard", value=f"[Access Here]({dashboard_link})", inline=True)
    embed.add_field(name="Library", value="discord.py", inline=True)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text="Created and Developed by X-Ample Development")

    await ctx.send(embed=embed)

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"User Info - {member}", color=discord.Color.blurple())
    embed.set_thumbnail(url=member.avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Name", value=member.display_name, inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"Server Info - {guild.name}", color=discord.Color.gold())
    embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Server ID", value=guild.id, inline=True)
    embed.add_field(name="Owner", value=guild.owner, inline=True)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Created On", value=guild.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    await ctx.send(embed=embed)
    
@bot.command()
@commands.has_permissions(manage_roles=True)
async def reactionrole(ctx, message_id: int, role: discord.Role, emoji: str):
    try:
        message = await ctx.fetch_message(message_id)
        await message.add_reaction(emoji)

        def check(payload):
            # Check if the reaction is added to the correct message and by the command invoker
            return payload.user_id == ctx.author.id and str(payload.emoji) == emoji and payload.message_id == message.id

        payload = await bot.wait_for('raw_reaction_add', check=check)

        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)

        if member:
            await member.add_roles(role)
        else:
            await ctx.send("Member not found.")

    except discord.NotFound:
        await ctx.send("Message not found. Please ensure the message ID is correct.")
    except discord.Forbidden:
        await ctx.send("I do not have permissions to manage roles.")
    except discord.HTTPException:
        await ctx.send("An error occurred while adding the reaction.")

@bot.command()
async def say(ctx, channel: discord.TextChannel = None, *, message):
    # Check if the user has permissions to delete messages
    if ctx.guild.me.guild_permissions.manage_messages:
        await ctx.message.delete()  # Delete the user's command message for cleaner chat
    
    # Determine the channel where the bot should send the message
    send_channel = channel if channel else ctx.channel
    
    # Send the message to the specified channel
    await send_channel.send(message)
    
# Run the bot
bot.run(os.getenv('DISCORD_TOKEN'))
