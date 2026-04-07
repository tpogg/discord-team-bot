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
logger = logging.getLogger("biohack-bot")
BOT_VERSION = "2.0.0-biohack"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))

WEBSITE_BEST = "https://bestpeptides.club"
WEBSITE_WARS = "https://peptidewars.com"

CHANNELS = {
    "general": "general-chat",
    "announcements": "announcements",
    "welcome_log": "welcome-log",
    "audit_log": "audit-log",
    "bot_commands": "bot-commands",
    "welcome": "welcome",
    "peptide_general": "peptide-general",
    "deals": "deals-and-discounts",
}

# ---------------------------------------------------------------------------
# Branding constants
# ---------------------------------------------------------------------------
BRAND_COLOR = 0x0D9488       # Teal — primary
BRAND_ACCENT = 0x22C55E      # Green — welcome / success
BRAND_WARN = 0xF59E0B        # Amber — tickets / warnings
BRAND_ANNOUNCE = 0xEF4444    # Red — announcements
BRAND_POLL = 0x8B5CF6        # Violet — polls
BRAND_INFO = 0x3B82F6        # Blue — info / resources
BRAND_PEPTIDE = 0x06B6D4     # Cyan — peptide-specific
BRAND_FOOTER = "bestpeptides.club | peptidewars.com"
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
    logger.info(f"{bot.user} is online | version {BOT_VERSION}")
    logger.info(f"GUILD_ID={GUILD_ID}")

    guild = bot.get_guild(GUILD_ID)

    # Sync slash commands — guild-specific if possible, global as fallback
    try:
        if guild:
            bot.tree.copy_global_to(guild=discord.Object(id=GUILD_ID))
            await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
            logger.info("Slash commands synced to guild")
        else:
            logger.warning(f"Guild {GUILD_ID} not found — syncing commands globally")
            await bot.tree.sync()
            logger.info("Slash commands synced globally (may take up to 1 hour)")
    except Exception:
        logger.exception("Failed to sync slash commands")

    if guild is None:
        return

    # Cache well-known channels
    for key, name in CHANNELS.items():
        ch = discord.utils.get(guild.text_channels, name=name)
        if ch:
            channel_cache[key] = ch
            logger.info(f"  Cached {key} -> #{name}")
        else:
            logger.warning(f"  Channel #{name} not found for key '{key}'")

    # Start daily check-in loop
    if not daily_checkin.is_running():
        daily_checkin.start()


@bot.event
async def on_member_join(member: discord.Member):
    try:
        # Auto-assign Member role
        role = discord.utils.get(member.guild.roles, name="Member")
        if role:
            await member.add_roles(role)

        # Welcome message
        ch = get_channel("welcome")
        if ch:
            embed = branded_embed(
                title=f"Welcome, {member.display_name}!",
                description=(
                    f"Hey {member.mention}, welcome to the **{member.guild.name}**!\n\n"
                    "1. Read **#rules** before posting\n"
                    "2. Introduce yourself in **#introductions** \u2014 what are you optimizing?\n"
                    "3. Browse **#guides-and-wikis** if you're new to peptides\n"
                    "4. Check out our sites:\n"
                    f"   \u2022 [{WEBSITE_BEST}]({WEBSITE_BEST})\n"
                    f"   \u2022 [{WEBSITE_WARS}]({WEBSITE_WARS})\n\n"
                    "Jump into **#peptide-general** or **#general-chat** and say hi!"
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
async def daily_checkin():
    """Daily community check-in posted to #general-chat on weekdays."""
    today = datetime.utcnow()
    if today.weekday() >= 5:  # Skip weekends
        return
    ch = get_channel("general")
    if not ch:
        return

    try:
        embed = branded_embed(
            title=f"Daily Check-In \u2014 {today.strftime('%A, %B %d')}",
            description=(
                "Drop your update in the thread:\n\n"
                "**Protocol:** What are you currently running?\n"
                "**Progress:** Any changes or results?\n"
                "**Questions:** Anything you need help with?"
            ),
        )
        msg = await ch.send(embed=embed)
        await msg.create_thread(
            name=f"Check-In {today.strftime('%m/%d')}",
            auto_archive_duration=1440,
        )
        logger.info("Daily check-in posted")
    except Exception:
        logger.exception("Failed to post daily check-in")


# ===================================================================
# Slash commands
# ===================================================================

# ---- /version -----------------------------------------------------

@bot.tree.command(name="version", description="Check which version of the bot is running")
async def version(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Running **{BOT_VERSION}**", ephemeral=True
    )


# ---- /help --------------------------------------------------------

@bot.tree.command(name="help", description="List all available bot commands")
async def help_command(interaction: discord.Interaction):
    commands_info = [
        ("`/help`", "Show this help message"),
        ("`/setup_server`", "Auto-create channels & roles from template *(Admin)*"),
        ("`/ticket`", "Open a question or support thread"),
        ("`/poll`", "Create a quick poll with 2\u20134 options"),
        ("`/log`", "Log a peptide or supplement protocol"),
        ("`/links`", "Get links to our websites and resources"),
        ("`/interest`", "Set your interest-area role"),
        ("`/announce`", "Post an announcement *(Moderator+)*"),
    ]
    desc = "\n".join(f"{cmd} \u2014 {info}" for cmd, info in commands_info)
    embed = branded_embed(
        title="Bot Commands",
        description=desc,
    )
    embed.add_field(
        name="Automatic features",
        value=(
            "- **Daily check-in** thread (weekdays at 2 PM UTC)\n"
            "- **Auto-onboarding** \u2014 new members get the Member role and a welcome message"
        ),
        inline=False,
    )
    embed.add_field(
        name="Our sites",
        value=f"[bestpeptides.club]({WEBSITE_BEST}) | [peptidewars.com]({WEBSITE_WARS})",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---- /links -------------------------------------------------------

@bot.tree.command(name="links", description="Get links to our websites and resources")
async def links(interaction: discord.Interaction):
    embed = branded_embed(
        title="Resources & Links",
        description=(
            f"**Best Peptides Club** \u2014 [{WEBSITE_BEST}]({WEBSITE_BEST})\n"
            f"**Peptide Wars** \u2014 [{WEBSITE_WARS}]({WEBSITE_WARS})\n\n"
            "**Community channels:**\n"
            "\u2022 **#peptide-general** \u2014 Open discussion\n"
            "\u2022 **#peptide-logs** \u2014 Share your protocols and results\n"
            "\u2022 **#sourcing-and-testing** \u2014 Vendors, COAs, and testing\n"
            "\u2022 **#research-and-studies** \u2014 PubMed links and papers\n"
            "\u2022 **#deals-and-discounts** \u2014 Sales and coupon codes"
        ),
        color=BRAND_INFO,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---- /ticket ------------------------------------------------------

@bot.tree.command(name="ticket", description="Open a question or support thread")
@app_commands.describe(
    category="Topic area",
    title="Brief title",
    description="Details or question",
)
@app_commands.choices(category=[
    app_commands.Choice(name="Peptides", value="peptides"),
    app_commands.Choice(name="Supplements / Nootropics", value="supps"),
    app_commands.Choice(name="Bloodwork / Labs", value="labs"),
    app_commands.Choice(name="Side Effects / Safety", value="safety"),
    app_commands.Choice(name="General", value="general"),
])
async def ticket(
    interaction: discord.Interaction,
    category: str,
    title: str,
    description: str,
):
    try:
        emoji = {
            "peptides": "\U0001f9ea",
            "supps": "\U0001f48a",
            "labs": "\U0001fa78",
            "safety": "\u26a0\ufe0f",
            "general": "\U0001f4cb",
        }.get(category, "\U0001f4cb")
        tid = f"Q-{datetime.utcnow().strftime('%y%m%d%H%M')}"

        embed = branded_embed(
            title=f"{emoji} [{tid}] {title}",
            description=description,
            color=BRAND_WARN,
        )
        embed.add_field(name="Topic", value=category.upper(), inline=True)
        embed.add_field(name="Status", value="Open", inline=True)
        embed.add_field(name="Asked by", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.create_thread(name=f"{tid} \u2014 {title}")
        await msg.add_reaction("\u2705")
        await msg.add_reaction("\U0001f440")
    except Exception:
        logger.exception("Error creating ticket")
        if not interaction.response.is_done():
            await interaction.response.send_message("Something went wrong.", ephemeral=True)


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
            await interaction.response.send_message("Something went wrong.", ephemeral=True)


# ---- /log ----------------------------------------------------------

@bot.tree.command(name="log", description="Log a peptide or supplement protocol")
@app_commands.describe(
    compound="What compound/peptide (e.g. BPC-157, Semaglutide)",
    dose="Dose and frequency (e.g. 250mcg 2x/day subQ)",
    duration="How long you've been running it",
    notes="Any notes, sides, or results",
)
async def log_protocol(
    interaction: discord.Interaction,
    compound: str,
    dose: str,
    duration: str = "Just started",
    notes: str = "No notes yet",
):
    try:
        embed = branded_embed(
            title=f"Protocol Log: {compound}",
            color=BRAND_PEPTIDE,
            author=interaction.user,
        )
        embed.add_field(name="Compound", value=compound, inline=True)
        embed.add_field(name="Dose", value=dose, inline=True)
        embed.add_field(name="Duration", value=duration, inline=True)
        embed.add_field(name="Notes", value=notes, inline=False)
        embed.add_field(
            name="Update template",
            value="Reply in the thread with updates as your cycle progresses.",
            inline=False,
        )

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.create_thread(
            name=f"{interaction.user.display_name} \u2014 {compound}",
            auto_archive_duration=10080,
        )
    except Exception:
        logger.exception("Error creating protocol log")
        if not interaction.response.is_done():
            await interaction.response.send_message("Something went wrong.", ephemeral=True)


# ---- /interest -----------------------------------------------------

@bot.tree.command(name="interest", description="Set your interest-area role")
@app_commands.describe(area="Choose your main interest")
@app_commands.choices(area=[
    app_commands.Choice(name="Peptides", value="Peptides"),
    app_commands.Choice(name="Longevity", value="Longevity"),
    app_commands.Choice(name="Nootropics", value="Nootropics"),
    app_commands.Choice(name="Fitness & Recovery", value="Fitness & Recovery"),
    app_commands.Choice(name="Hormone Optimization", value="Hormone Optimization"),
])
async def interest(interaction: discord.Interaction, area: str):
    try:
        interest_roles = [
            "Peptides", "Longevity", "Nootropics",
            "Fitness & Recovery", "Hormone Optimization",
        ]

        # Remove any existing interest role
        for r in interaction.user.roles:
            if r.name in interest_roles:
                await interaction.user.remove_roles(r)

        # Assign selected interest role (create if missing)
        role = discord.utils.get(interaction.guild.roles, name=area)
        if not role:
            role = await interaction.guild.create_role(name=area, mentionable=True)
        await interaction.user.add_roles(role)

        await interaction.response.send_message(
            f"You're tagged as **{area}**!", ephemeral=True
        )
    except Exception:
        logger.exception("Error setting interest role")
        if not interaction.response.is_done():
            await interaction.response.send_message("Something went wrong.", ephemeral=True)


# ---- /announce -----------------------------------------------------

@bot.tree.command(name="announce", description="Post an announcement (Moderator+)")
@app_commands.describe(title="Title", message="Body")
async def announce(interaction: discord.Interaction, title: str, message: str):
    if not any(r.name in ["Admin", "Moderator"] for r in interaction.user.roles):
        await interaction.response.send_message("Moderator+ only.", ephemeral=True)
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
            await interaction.response.send_message("Something went wrong.", ephemeral=True)


# ---- /setup_server -------------------------------------------------

@bot.tree.command(
    name="setup_server",
    description="Wipe old channels/roles and rebuild server from template (Admin only)",
)
@app_commands.describe(
    clean="Delete channels and roles not in the template? (default: True)",
)
async def setup_server(
    interaction: discord.Interaction,
    clean: bool = True,
):
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

    # Build sets of names the template expects
    template_role_names = {rd["name"] for rd in template["roles"]}
    template_category_names = {cat["name"] for cat in template["categories"]}
    template_channel_names: set[str] = set()
    for cat in template["categories"]:
        for cd in cat.get("channels", []):
            template_channel_names.add(cd["name"])

    # Roles that should never be touched
    protected_roles = {"@everyone", "Server Booster"}

    # ------ Clean phase: remove old stuff ------
    if clean:
        # Delete channels not in template (skip uncategorized channels)
        for ch in list(guild.channels):
            if ch.name not in template_channel_names and ch.name not in template_category_names:
                # Skip the "general" default channel Discord won't let you delete
                if isinstance(ch, discord.TextChannel) and ch.position == 0 and ch.category is None:
                    continue
                try:
                    await ch.delete(reason="setup_server clean")
                    status.append(f"- Deleted #{ch.name}")
                except Exception:
                    logger.warning(f"Could not delete channel {ch.name}")

        # Delete roles not in template
        for r in list(guild.roles):
            if r.name in protected_roles or r.is_default() or r.managed:
                continue
            if r.name not in template_role_names:
                try:
                    await r.delete(reason="setup_server clean")
                    status.append(f"- Deleted role: {r.name}")
                except Exception:
                    logger.warning(f"Could not delete role {r.name}")

        # Small delay to let Discord catch up
        await asyncio.sleep(1)

    # ------ Create roles ------
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

    # ------ Create channels & set permissions ------
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
        # Re-check existing channels after clean phase
        current_ch = {c.name for c in guild.channels}
        for cd in cat.get("channels", []):
            if cd["name"] not in current_ch:
                if cd.get("type") == "voice":
                    await guild.create_voice_channel(
                        cd["name"],
                        category=category,
                        user_limit=cd.get("user_limit", 0),
                    )
                else:
                    await guild.create_text_channel(
                        cd["name"],
                        category=category,
                        topic=cd.get("topic", ""),
                    )
                status.append(f"  + #{cd['name']}")
            else:
                status.append(f"  = #{cd['name']}")

        # Make #announcements read-only for Members
        if cat["name"] == "\u2501\u2501 WELCOME \u2501\u2501":
            ann_ch = discord.utils.get(guild.text_channels, name="announcements")
            if ann_ch:
                member_role = role_objects.get("Member") or discord.utils.get(
                    guild.roles, name="Member"
                )
                if member_role:
                    await ann_ch.set_permissions(
                        member_role,
                        view_channel=True,
                        send_messages=False,
                        add_reactions=True,
                        read_message_history=True,
                    )
                status.append("  Announcements: read-only for members")

    logger.info("Server setup completed")
    await interaction.followup.send(
        f"**Setup Complete:**\n```\n{chr(10).join(status[:60])}\n```"
    )


# ===================================================================
# Run
# ===================================================================

if __name__ == "__main__":
    bot.run(TOKEN)
