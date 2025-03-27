import discord
from discord.ext import commands

# USED DATA FILE TO HOLD IDS AND TOKENS
from data import *  

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"BOT IS ONLINE AS {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return  # Don't delete bot messages

    if message.channel.id == CHANNEL_ID:
        await message.delete(delay=30)  # Delete after 30 seconds

    await bot.process_commands(message)

bot.run(TOKEN)
