import discord
from discord.ext import commands
import datetime
import random
import string
import sqlite3
import secrets
import string

# Create / connect database
conn = sqlite3.connect("keys.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS keys (
    key TEXT PRIMARY KEY,
    created_by INTEGER,
    used INTEGER DEFAULT 0,
    used_by INTEGER
)
""")

conn.commit()

import os
TOKEN = os.getenv("TOKEN") #using this because of hosting
#TOKEN = "tone is here"
OWNER_ID = 1313838404844130307
ROLE_ID = 1477159527366393987
INVITE_CHANNEL_ID = 1477161537159299092
LOGIN_CHANNEL_ID = 1477161753753292964
LOG_CHANNEL_ID = 1477167972421337302
GENERATOR_ROLE_ID = 1477407727021068500

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

invite_cooldowns = {}

# Generate 5566- + 16 characters
def generate_key():
    random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    return f"5566-{random_part}"

def has_generator_role(member: discord.Member):
    return any(role.id == GENERATOR_ROLE_ID for role in member.roles)


async def ensure_panel(channel_id, embed, view):
    channel = bot.get_channel(channel_id)
    if channel is None:
        return

    async for message in channel.history(limit=20):
        if message.author == bot.user and message.components:
            return  # Panel already exists

    await channel.send(embed=embed, view=view)


# ================= LOGIN SYSTEM =================

class LoginModal(discord.ui.Modal, title="Enter Key"):
    key_input = discord.ui.TextInput(
        label="Paste your key below",
        placeholder="5566-xxxxxxxxxxxxxxxx",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):

        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ Cannot be used in DMs.",
                ephemeral=True
            )
            return

        role = interaction.guild.get_role(ROLE_ID)

        if role is None:
            await interaction.response.send_message(
                "❌ Role not found.",
                ephemeral=True
            )
            return

        if role in interaction.user.roles:
            await interaction.response.send_message(
                "You al have access.",
                ephemeral=True
            )
            return

        key = self.key_input.value.strip()

        cursor.execute("SELECT used, created_by FROM keys WHERE key = ?", (key,))
        result = cursor.fetchone()

        if not result:
            await interaction.response.send_message(
                "❌ Invalid key.",
                ephemeral=True
            )
            return

        if result[0] == 1:
            await interaction.response.send_message(
                "❌ This key has al been used.",
                ephemeral=True
            )
            return

        # Defer BEFORE doing role + database update
        await interaction.response.defer(ephemeral=True)

        cursor.execute(
            "UPDATE keys SET used = 1, used_by = ? WHERE key = ?",
            (interaction.user.id, key)
        )
        conn.commit()

        used_status, creator_id = result

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            generator = interaction.guild.get_member(creator_id)
            generator_mention = generator.mention if generator else f"<@{creator_id}>"
        
            await log_channel.send(
                f'Key used "{key}" by {interaction.user.mention} | generator {generator_mention}'
            )

        await interaction.user.add_roles(role)

        await interaction.followup.send(
            "✅ Key valid. Role granted.",
            ephemeral=True
        )

class LoginView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Login",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_login_button"
    )
    async def login_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LoginModal())
        role = interaction.guild.get_role(ROLE_ID)

        # Block users with role
        if role in interaction.user.roles:
            await interaction.response.send_message(
                "You al have access.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(LoginModal())

@bot.command()
async def loginsystem(ctx):
    if ctx.author.id != OWNER_ID:
        return

    embed = discord.Embed(
        title="Login System",
        description="Press the button to paste the key inside.",
        color=discord.Color.blue()
    )

    await ctx.send(embed=embed, view=LoginView())

# ================= GENERATOR KEY =================

@bot.command()
async def generatekey(ctx, amount: int):
    # Role restriction
    if not has_generator_role(ctx.author):
        return

    # Basic validation
    if amount <= 0 or amount > 50:
        return

    keys = []

    for _ in range(amount):
        key = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))

        cursor.execute(
            "INSERT INTO keys (key, generator_id, used) VALUES (?, ?, 0)",
            (key, ctx.author.id)
        )
        conn.commit()

        keys.append(key)

    try:
        await ctx.author.send("\n".join(keys))
    except discord.Forbidden:
        pass

# ================= INVITE SYSTEM =================

class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Generate",
        style=discord.ButtonStyle.success,
        custom_id="persistent_invite_generate"
    )
    async def generate_button(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(ROLE_ID)

        # Only role holders can generate
        if role not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ You must have the required role to generate a key.",
                ephemeral=True
            )
            return

        user_id = interaction.user.id
        now = datetime.datetime.utcnow()

        if user_id in invite_cooldowns:
            next_allowed = invite_cooldowns[user_id]
            if now < next_allowed:
                remaining = next_allowed - now
                days_left = remaining.days
                await interaction.response.send_message(
                    f"You must wait {days_left} more day(s).",
                    ephemeral=True
                )
                return

        new_key = generate_key()

        # Store in database
        cursor.execute(
            "INSERT INTO keys (key, created_by, used) VALUES (?, ?, 0)",
            (new_key, user_id)
        )
        conn.commit()

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(
                f'Key generated by {interaction.user.mention} "{new_key}"'
            )

        invite_cooldowns[user_id] = now + datetime.timedelta(days=3)

        try:
            await interaction.user.send(
                f"🔑 Your invite key:\n`{new_key}`\n\nThis key can only be used once."
            )
            await interaction.response.send_message(
                "✅ Key sent to your DMs.",
                ephemeral=True
            )
        except:
            await interaction.response.send_message(
                "❌ I cannot DM you. Please enable DMs.",
                ephemeral=True
            )

@bot.command()
async def invitesystem(ctx):
    if ctx.author.id != OWNER_ID:
        return

    embed = discord.Embed(
        title="Invite System",
        description="Press the button to generate an invite key (You can only generate 1 key every 3 days)",
        color=discord.Color.green()
    )

    await ctx.send(embed=embed, view=InviteView())

# ================= ADD MEMBER =================

@bot.command()
async def addmember(ctx, member: discord.Member):
    if ctx.author.id != OWNER_ID:
        return

    role = ctx.guild.get_role(ROLE_ID)

    if role is None:
        await ctx.send("Role not found.")
        return

    await member.add_roles(role)
    await ctx.send(f"{member.mention} has been given the role.")

# ================= READY =================

@bot.event
async def on_ready():
    bot.add_view(InviteView())
    bot.add_view(LoginView())

    invite_embed = discord.Embed(
        title="Invite System",
        description="Press the button to generate an invite key (1 key every 3 days)",
        color=discord.Color.green()
    )

    login_embed = discord.Embed(
        title="Login System",
        description="Press the button to paste the key inside.",
        color=discord.Color.blue()
    )

    await ensure_panel(INVITE_CHANNEL_ID, invite_embed, InviteView())
    await ensure_panel(LOGIN_CHANNEL_ID, login_embed, LoginView())

    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
