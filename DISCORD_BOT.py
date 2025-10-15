from discord.ext import commands
import discord
from pathlib import Path
import asyncio
from data import TOKEN

intents = discord.Intents.default()
intents.message_content = True  # Required for reading messages (if needed)
intents.members = True          # Enable member events
intents.guilds = True           # Usually already enabled
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    try:
        # 🔹 Register commands only after bot is ready
        synced = await bot.tree.sync()
        print(f"🌐 Synced {len(synced)} global command(s).")
    except Exception as e:
        print(f"⚠️ Failed to sync app commands: {e}")

# ✅ Automatically load all .py files in the /cogs folder
async def load_extensions():
    for file in Path("cogs").glob("*.py"):
        if not file.name.startswith("_"):
            extension = f"cogs.{file.stem}"
            try:
                await bot.load_extension(extension)
                print(f"✅ Loaded extension: {extension}")
            except Exception as e:
                print(f"❌ Failed to load extension {extension}: {e}")

# 📦 Entry point
async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

# 🔥 Start the bot
asyncio.run(main())
