import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import json, os, asyncio

TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))
CHANNELS = {"standup":"daily-standup","announcements":"announcements","welcome_log":"welcome-log","audit_log":"audit-log","bot_commands":"bot-commands","welcome":"welcome"}

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
channel_cache = {}

def get_channel(key):
    return channel_cache.get(key)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online")
    guild = bot.get_guild(GUILD_ID)
    if guild:
        for key, name in CHANNELS.items():
            ch = discord.utils.get(guild.text_channels, name=name)
            if ch:
                channel_cache[key] = ch
                print(f"  📌 {key} → #{name}")
        bot.tree.copy_global_to(guild=discord.Object(id=GUILD_ID))
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("  🔄 Slash commands synced")
    if not standup_reminder.is_running():
        standup_reminder.start()

@bot.event
async def on_member_join(member):
    role = discord.utils.get(member.guild.roles, name="Team Member")
    if role: await member.add_roles(role)
    ch = get_channel("welcome")
    if ch:
        embed = discord.Embed(title=f"Welcome, {member.display_name}! 👋",description=f"Hey {member.mention}, welcome to **{member.guild.name}**!\n\n1️⃣ Read **#rules-and-guidelines**\n2️⃣ Introduce yourself in **#introductions**\n3️⃣ Check **#docs-and-links** for resources\n4️⃣ Join **#daily-standup** to stay in sync",color=0x2ECC71,timestamp=datetime.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        await ch.send(embed=embed)
    log = get_channel("welcome_log")
    if log: await log.send(f"📥 **{member.display_name}** joined • {member.mention} • Created: {member.created_at.strftime('%Y-%m-%d')}")

@bot.event
async def on_member_remove(member):
    log = get_channel("welcome_log")
    if log: await log.send(f"📤 **{member.display_name}** left the server")

@tasks.loop(time=time(hour=14, minute=0))
async def standup_reminder():
    today = datetime.utcnow()
    if today.weekday() >= 5: return
    ch = get_channel("standup")
    if not ch: return
    embed = discord.Embed(title=f"🌅 Daily Standup — {today.strftime('%A, %B %d')}",description="Reply in the thread:\n\n**✅ Yesterday:** What did you accomplish?\n**📋 Today:** What are you working on?\n**🚧 Blockers:** Anything in your way?",color=0x3498DB)
    msg = await ch.send(embed=embed)
    await msg.create_thread(name=f"Standup {today.strftime('%m/%d')}",auto_archive_duration=1440)

@bot.tree.command(name="ticket", description="Create a support/request ticket")
@app_commands.describe(category="Ticket category",title="Brief title",description="Detailed description")
@app_commands.choices(category=[app_commands.Choice(name="IT / Access Request",value="it"),app_commands.Choice(name="HR / People",value="hr"),app_commands.Choice(name="Bug Report",value="bug"),app_commands.Choice(name="Feature Request",value="feature"),app_commands.Choice(name="General",value="general")])
async def ticket(interaction, category: str, title: str, description: str):
    emoji_map = {"it":"🔧","hr":"👤","bug":"🐛","feature":"💡","general":"📋"}
    tid = f"T-{datetime.utcnow().strftime('%y%m%d%H%M')}"
    embed = discord.Embed(title=f"{emoji_map.get(category,'📋')} [{tid}] {title}",description=description,color=0xE67E22,timestamp=datetime.utcnow())
    embed.add_field(name="Category",value=category.upper(),inline=True)
    embed.add_field(name="Status",value="🟡 Open",inline=True)
    embed.add_field(name="Submitted by",value=interaction.user.mention,inline=True)
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    await msg.create_thread(name=f"{tid} — {title}")
    await msg.add_reaction("✅"); await msg.add_reaction("👀")

@bot.tree.command(name="poll", description="Create a quick poll")
@app_commands.describe(question="The poll question",option1="Option 1",option2="Option 2",option3="Option 3 (optional)",option4="Option 4 (optional)")
async def poll(interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣"]
    options = [o for o in [option1, option2, option3, option4] if o]
    desc = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))
    embed = discord.Embed(title=f"📊 {question}",description=desc,color=0x9B59B6,timestamp=datetime.utcnow())
    embed.set_footer(text=f"Poll by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    for i in range(len(options)): await msg.add_reaction(emojis[i])

@bot.tree.command(name="meeting", description="Start a meeting notes thread")
@app_commands.describe(title="Meeting title",attendees="Tag attendees",agenda="Agenda items")
async def meeting(interaction, title: str, attendees: str = "Everyone", agenda: str = "Open discussion"):
    now = datetime.utcnow()
    embed = discord.Embed(title=f"📝 {title}",color=0x1ABC9C,timestamp=now)
    embed.add_field(name="Date",value=now.strftime("%B %d, %Y"),inline=True)
    embed.add_field(name="Attendees",value=attendees,inline=True)
    embed.add_field(name="Agenda",value=agenda,inline=False)
    embed.add_field(name="Template",value="**Decisions Made:**\n**Action Items:**\n**Follow-ups:**",inline=False)
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    await msg.create_thread(name=f"Notes — {title} ({now.strftime('%m/%d')})",auto_archive_duration=10080)

@bot.tree.command(name="department", description="Set your department role")
@app_commands.describe(dept="Choose your department")
@app_commands.choices(dept=[app_commands.Choice(name="Engineering",value="Engineering"),app_commands.Choice(name="Design",value="Design"),app_commands.Choice(name="Marketing",value="Marketing"),app_commands.Choice(name="Sales",value="Sales"),app_commands.Choice(name="Operations",value="Operations")])
async def department(interaction, dept: str):
    dept_roles = ["Engineering","Design","Marketing","Sales","Operations"]
    for r in interaction.user.roles:
        if r.name in dept_roles: await interaction.user.remove_roles(r)
    role = discord.utils.get(interaction.guild.roles, name=dept)
    if not role: role = await interaction.guild.create_role(name=dept, mentionable=True)
    await interaction.user.add_roles(role)
    await interaction.response.send_message(f"✅ You're now in **{dept}**!", ephemeral=True)

@bot.tree.command(name="announce", description="Post an announcement (Manager+)")
@app_commands.describe(title="Title",message="Body")
async def announce(interaction, title: str, message: str):
    if not any(r.name in ["Admin","Manager"] for r in interaction.user.roles):
        await interaction.response.send_message("❌ Manager+ only.", ephemeral=True); return
    ch = get_channel("announcements")
    if not ch: await interaction.response.send_message("❌ #announcements not found.", ephemeral=True); return
    embed = discord.Embed(title=f"📢 {title}",description=message,color=0xE74C3C,timestamp=datetime.utcnow())
    embed.set_footer(text=f"Posted by {interaction.user.display_name}")
    await ch.send(embed=embed)
    await interaction.response.send_message("✅ Posted!", ephemeral=True)

@bot.tree.command(name="setup_server", description="Auto-create channels & roles from template (Admin only)")
async def setup_server(interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    template_path = os.path.join(os.path.dirname(__file__), "server-template.json")
    if not os.path.exists(template_path):
        await interaction.followup.send("❌ server-template.json not found."); return
    with open(template_path) as f: template = json.load(f)
    status = []
    existing_roles = {r.name for r in guild.roles}
    for rd in template["roles"]:
        if rd["name"] not in existing_roles:
            await guild.create_role(name=rd["name"],color=discord.Color(int(rd["color"].lstrip("#"),16)),hoist=rd.get("hoist",False),mentionable=rd.get("mentionable",False))
            status.append(f"✅ Role: {rd['name']}")
        else: status.append(f"⏭️ Role: {rd['name']}")
    existing_ch = {c.name for c in guild.channels}
    for cat in template["categories"]:
        if cat["name"] not in existing_ch:
            category = await guild.create_category(cat["name"])
            status.append(f"✅ {cat['name']}")
        else:
            category = discord.utils.get(guild.categories, name=cat["name"])
            status.append(f"⏭️ {cat['name']}")
        if category:
            for cd in cat.get("channels",[]):
                if cd["name"] not in existing_ch:
                    if cd.get("type")=="voice": await guild.create_voice_channel(cd["name"],category=category,user_limit=cd.get("user_limit",0))
                    else: await guild.create_text_channel(cd["name"],category=category,topic=cd.get("topic",""))
                    status.append(f"  ✅ #{cd['name']}")
                else: status.append(f"  ⏭️ #{cd['name']}")
    await interaction.followup.send(f"**Setup Complete:**\n```\n{chr(10).join(status[:40])}\n```")

if __name__ == "__main__":
    bot.run(TOKEN)
