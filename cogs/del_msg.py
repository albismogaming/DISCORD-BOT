from discord.ext import commands
# Import your constants like CHANNEL_ID
from data import CHANNEL_ID

class MessageCleanup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot and message.author != message.guild.me:
            return

        if message.channel.id == CHANNEL_ID:
            await message.delete(delay=30)  # Adjust time as needed

# 👇 MUST be async now
async def setup(bot):
    await bot.add_cog(MessageCleanup(bot))  # 👈 also MUST be awaited
