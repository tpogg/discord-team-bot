import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import json
import os
import asyncio
import logging

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("team-bot")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))

CHANNELS = {
    "standup": "daily-standup",
    "announcements": "announcements",
    "welcome_log": "welcome-log",
    "audit_log": "audit-log",
    "bot_commands": "bot-commands",
    "welcome": "welcome",
}

# ---------------------------------------------------------------------------
# Branding constants
# ---------------------------------------------------------------------------
BRAND_COLOR = 0x2B6CB0       # Primary blue
BRAND_ACCENT = 0x38A169      # Green accent (success / welcome)
BRAND_WARN = 0xE67E22        # Orange (tickets, warnings)
BRAND_ANNOUNCE = 0xE53E3E    # Red (announcements)
BRAND_POLL = 0x805AD5        # Purple (polls)
BRAND_MEETING = 0x319795     # Teal (meetings)
BRAND_FOOTER = "Team Bot"
BRAND_ICON = None  # Set a URL string here to add a footer icon

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
channel_cache: dict[str, discord.TextChannel] = {}


def get_channel(key: str) -> discord.TextChannel | None:
    """Return a cached channel by its logical key."""
    return channel_cache.get(key)


def branded_embed(
    title: str,
    description: str = "",
    color: int = BRAND_COLOR,
    *,
    author: discord.Member | None = None,
) -> discord.Embed:
    """Create an embed with consistent branding applied."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow(),
    )
    embed.set_footer(text=BRAND_FOOTER, icon_url=BRAND_ICON)
    if author:
        embed.set_thumbnail(url=author.display_avatar.url)
    return embed


# ===================================================================
# Events
# ===================================================================

@bot.event
async def on_ready():
    logger.info(f"{bot.user} is online")
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        logger.warning(f"Guild {GUILD_ID} not found")
        return

    # Cache well-known channels
    for key, name in CHANNELS.items():
        ch = discord.utils.get(guild.text_channels, name=name)
        if ch:
            channel_cache[key] = ch
            logger.info(f"  Cached {key} -> #{name}")
        else:
            logger.warning(f"  Channel #{name} not found for key '{key}'")

    # Sync slash commands to the guild
    try:
        bot.tree.copy_global_to(guild=discord.Object(id=GUILD_ID))
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        logger.info("Slash commands synced")
    except Exception:
        logger.exception("Failed to sync slash commands")

    # Start standup reminder loop
    if not standup_reminder.is_running():
        standup_reminder.start()


@bot.event
async def on_member_join(member: discord.Member):
    try:
        # Auto-assign Team Member role
        role = discord.utils.get(member.guild.roles, name="Team Member")
        if role:
            await member.add_roles(role)

        # Welcome message
        ch = get_channel("welcome")
        if ch:
            embed = branded_embed(
                title=f"Welcome, {member.display_name}!",
                description=(
                    f"Hey {member.mention}, welcome to **{member.guild.name}**!\n\n"
                    "1. Read **#rules-and-guidelines**\n"
                    "2. Introduce yourself in **#introductions**\n"
                    "3. Check **#docs-and-links** for resources\n"
                    "4. Join **#daily-standup** to stay in sync"
                ),
                color=BRAND_ACCENT,
                author=member,
            )
            await ch.send(embed=embed)

        # Internal log
        log = get_channel("welcome_log")
        if log:
            await log.send(
                f"**{member.display_name}** joined | {member.mention} | "
                f"Account created: {member.created_at.strftime('%Y-%m-%d')}"
            )
    except Exception:
        logger.exception(f"Error handling member join for {member}")


@bot.event
async def on_member_remove(member: discord.Member):
    try:
        log = get_channel("welcome_log")
        if log:
            await log.send(f"**{member.display_name}** left the server")
    except Exception:
        logger.exception(f"Error handling member remove for {member}")


# ===================================================================
# Scheduled tasks
# ===================================================================

@tasks.loop(time=time(hour=14, minute=0))
async def standup_reminder():
    today = datetime.utcnow()
    if today.weekday() >= 5:  # Skip weekends
        return
    ch = get_channel("standup")
    if not ch:
        return

    try:
        embed = branded_embed(
            title=f"Daily Standup \u2014 {today.strftime('%A, %B %d')}",
            description=(
                "Reply in the thread:\n\n"
                "**Yesterday:** What did you accomplish?\n"
                "**Today:** What are you working on?\n"
                "**Blockers:** Anything in your way?"
            ),
        )
        msg = await ch.send(embed=embed)
        await msg.create_thread(
            name=f"Standup {today.strftime('%m/%d')}",
            auto_archive_duration=1440,
        )
        logger.info("Standup reminder posted")
    except Exception:
        logger.exception("Failed to post standup reminder")


# ===================================================================
# Slash commands
# ===================================================================

# ---- /help --------------------------------------------------------

@bot.tree.command(name="help", description="List all available bot commands")
async def help_command(interaction: discord.Interaction):
    commands_info = [
        ("`/help`", "Show this help message"),
        ("`/setup_server`", "Auto-create channels & roles from template *(Admin)*"),
        ("`/ticket`", "Create a support or request ticket"),
        ("`/poll`", "Create a quick poll with 2\u20134 options"),
        ("`/meeting`", "Start a meeting-notes thread"),
        ("`/department`", "Set your department role"),
        ("`/announce`", "Post an announcement *(Manager+)*"),
    ]
    desc = "\n".join(f"{cmd} \u2014 {info}" for cmd, info in commands_info)
    embed = branded_embed(
        title="Bot Commands",
        description=desc,
    )
    embed.add_field(
        name="Automatic features",
        value=(
            "- **Daily standup** reminders (weekdays at 2 PM UTC)\n"
            "- **Auto-onboarding** \u2014 new members get the Team Member role and a welcome message"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---- /ticket ------------------------------------------------------

@bot.tree.command(name="ticket", description="Create a support/request ticket")
@app_commands.describe(
    category="Ticket category",
    title="Brief title",
    description="Detailed description",
)
@app_commands.choices(category=[
    app_commands.Choice(name="IT / Access Request", value="it"),
    app_commands.Choice(name="HR / People", value="hr"),
    app_commands.Choice(name="Bug Report", value="bug"),
    app_commands.Choice(name="Feature Request", value="feature"),
    app_commands.Choice(name="General", value="general"),
])
async def ticket(
    interaction: discord.Interaction,
    category: str,
    title: str,
    description: str,
):
    try:
        emoji_map = {"it": "wrench", "hr": "person", "bug": "bug", "feature": "bulb", "general": "clipboard"}
        emoji = {"it": "\U0001f527", "hr": "\U0001f464", "bug": "\U0001f41b", "feature": "\U0001f4a1", "general": "\U0001f4cb"}.get(category, "\U0001f4cb")
        tid = f"T-{datetime.utcnow().strftime('%y%m%d%H%M')}"

        embed = branded_embed(
            title=f"{emoji} [{tid}] {title}",
            description=description,
            color=BRAND_WARN,
        )
        embed.add_field(name="Category", value=category.upper(), inline=True)
        embed.add_field(name="Status", value="Open", inline=True)
        embed.add_field(name="Submitted by", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.create_thread(name=f"{tid} \u2014 {title}")
        await msg.add_reaction("\u2705")
        await msg.add_reaction("\U0001f440")
    except Exception:
        logger.exception("Error creating ticket")
        if not interaction.response.is_done():
            await interaction.response.send_message("Something went wrong creating the ticket.", ephemeral=True)


# ---- /poll ---------------------------------------------------------

@bot.tree.command(name="poll", description="Create a quick poll")
@app_commands.describe(
    question="The poll question",
    option1="Option 1",
    option2="Option 2",
    option3="Option 3 (optional)",
    option4="Option 4 (optional)",
)
async def poll(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: str = None,
    option4: str = None,
):
    try:
        emojis = ["1\ufe0f\u20e3", "2\ufe0f\u20e3", "3\ufe0f\u20e3", "4\ufe0f\u20e3"]
        options = [o for o in [option1, option2, option3, option4] if o]
        desc = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))

        embed = branded_embed(
            title=f"Poll: {question}",
            description=desc,
            color=BRAND_POLL,
            author=interaction.user,
        )

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])
    except Exception:
        logger.exception("Error creating poll")
        if not interaction.response.is_done():
            await interaction.response.send_message("Something went wrong creating the poll.", ephemeral=True)


# ---- /meeting ------------------------------------------------------

@bot.tree.command(name="meeting", description="Start a meeting notes thread")
@app_commands.describe(
    title="Meeting title",
    attendees="Tag attendees",
    agenda="Agenda items",
)
async def meeting(
    interaction: discord.Interaction,
    title: str,
    attendees: str = "Everyone",
    agenda: str = "Open discussion",
):
    try:
        now = datetime.utcnow()
        embed = branded_embed(
            title=f"Meeting: {title}",
            color=BRAND_MEETING,
        )
        embed.add_field(name="Date", value=now.strftime("%B %d, %Y"), inline=True)
        embed.add_field(name="Attendees", value=attendees, inline=True)
        embed.add_field(name="Agenda", value=agenda, inline=False)
        embed.add_field(
            name="Template",
            value="**Decisions Made:**\n**Action Items:**\n**Follow-ups:**",
            inline=False,
        )

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.create_thread(
            name=f"Notes \u2014 {title} ({now.strftime('%m/%d')})",
            auto_archive_duration=10080,
        )
    except Exception:
        logger.exception("Error creating meeting")
        if not interaction.response.is_done():
            await interaction.response.send_message("Something went wrong creating the meeting.", ephemeral=True)


# ---- /department ---------------------------------------------------

@bot.tree.command(name="department", description="Set your department role")
@app_commands.describe(dept="Choose your department")
@app_commands.choices(dept=[
    app_commands.Choice(name="Engineering", value="Engineering"),
    app_commands.Choice(name="Design", value="Design"),
    app_commands.Choice(name="Marketing", value="Marketing"),
    app_commands.Choice(name="Sales", value="Sales"),
    app_commands.Choice(name="Operations", value="Operations"),
])
async def department(interaction: discord.Interaction, dept: str):
    try:
        dept_roles = ["Engineering", "Design", "Marketing", "Sales", "Operations"]

        # Remove any existing department role
        for r in interaction.user.roles:
            if r.name in dept_roles:
                await interaction.user.remove_roles(r)

        # Assign selected department role (create if missing)
        role = discord.utils.get(interaction.guild.roles, name=dept)
        if not role:
            role = await interaction.guild.create_role(name=dept, mentionable=True)
        await interaction.user.add_roles(role)

        await interaction.response.send_message(
            f"You're now in **{dept}**!", ephemeral=True
        )
    except Exception:
        logger.exception("Error setting department")
        if not interaction.response.is_done():
            await interaction.response.send_message("Something went wrong setting your department.", ephemeral=True)


# ---- /announce -----------------------------------------------------

@bot.tree.command(name="announce", description="Post an announcement (Manager+)")
@app_commands.describe(title="Title", message="Body")
async def announce(interaction: discord.Interaction, title: str, message: str):
    if not any(r.name in ["Admin", "Manager"] for r in interaction.user.roles):
        await interaction.response.send_message("Manager+ only.", ephemeral=True)
        return

    ch = get_channel("announcements")
    if not ch:
        await interaction.response.send_message("#announcements not found.", ephemeral=True)
        return

    try:
        embed = branded_embed(
            title=f"Announcement: {title}",
            description=message,
            color=BRAND_ANNOUNCE,
            author=interaction.user,
        )
        await ch.send(embed=embed)
        await interaction.response.send_message("Posted!", ephemeral=True)
    except Exception:
        logger.exception("Error posting announcement")
        if not interaction.response.is_done():
            await interaction.response.send_message("Something went wrong posting the announcement.", ephemeral=True)


# ---- /setup_server -------------------------------------------------

@bot.tree.command(
    name="setup_server",
    description="Auto-create channels, roles & permissions from template (Admin only)",
)
async def setup_server(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    # Load template
    template_path = os.path.join(os.path.dirname(__file__), "server-template.json")
    if not os.path.exists(template_path):
        await interaction.followup.send("server-template.json not found.")
        return

    with open(template_path) as f:
        template = json.load(f)

    status: list[str] = []

    # ------ Roles ------
    existing_roles = {r.name: r for r in guild.roles}
    role_objects: dict[str, discord.Role] = {}

    for rd in template["roles"]:
        if rd["name"] not in existing_roles:
            role = await guild.create_role(
                name=rd["name"],
                color=discord.Color(int(rd["color"].lstrip("#"), 16)),
                hoist=rd.get("hoist", False),
                mentionable=rd.get("mentionable", False),
            )
            role_objects[rd["name"]] = role
            status.append(f"+ Role: {rd['name']}")
        else:
            role_objects[rd["name"]] = existing_roles[rd["name"]]
            status.append(f"= Role: {rd['name']}")

    # ------ Channels & permissions ------
    existing_ch = {c.name: c for c in guild.channels}

    for cat in template["categories"]:
        # Create or fetch category
        if cat["name"] not in existing_ch:
            category = await guild.create_category(cat["name"])
            status.append(f"+ {cat['name']}")
        else:
            category = discord.utils.get(guild.categories, name=cat["name"])
            status.append(f"= {cat['name']}")

        if category is None:
            continue

        # Apply category-level permission overwrites for restricted categories
        restricted_to = cat.get("restricted_to")
        if restricted_to:
            overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False,
                ),
            }
            for role_name in restricted_to:
                role = role_objects.get(role_name) or discord.utils.get(guild.roles, name=role_name)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                    )
            try:
                await category.edit(overwrites=overwrites)
                status.append(f"  Locked to: {', '.join(restricted_to)}")
            except Exception:
                logger.exception(f"Failed to set overwrites on {cat['name']}")

        # Create channels inside the category
        for cd in cat.get("channels", []):
            if cd["name"] not in existing_ch:
                if cd.get("type") == "voice":
                    new_ch = await guild.create_voice_channel(
                        cd["name"],
                        category=category,
                        user_limit=cd.get("user_limit", 0),
                    )
                else:
                    new_ch = await guild.create_text_channel(
                        cd["name"],
                        category=category,
                        topic=cd.get("topic", ""),
                    )
                status.append(f"  + #{cd['name']}")
            else:
                new_ch = existing_ch[cd["name"]]
                status.append(f"  = #{cd['name']}")

        # Make #announcements read-only for Team Member / Contractor
        if cat["name"] == "\u2501\u2501 WELCOME \u2501\u2501":
            ann_ch = discord.utils.get(guild.text_channels, name="announcements")
            if ann_ch:
                for viewer_role_name in ["Team Member", "Contractor"]:
                    viewer_role = role_objects.get(viewer_role_name) or discord.utils.get(
                        guild.roles, name=viewer_role_name
                    )
                    if viewer_role:
                        await ann_ch.set_permissions(
                            viewer_role,
                            view_channel=True,
                            send_messages=False,
                            add_reactions=True,
                            read_message_history=True,
                        )
                status.append("  Announcements: read-only for members")

    logger.info("Server setup completed")
    await interaction.followup.send(
        f"**Setup Complete:**\n```\n{chr(10).join(status[:50])}\n```"
    )


# ===================================================================
# Run
# ===================================================================

if __name__ == "__main__":
    bot.run(TOKEN)
