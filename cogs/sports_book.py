import random
import requests
from discord.ext import commands
from utils.mlb_scores import get_mlb_scores  # or import directly if in same file

class MLBScores(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def mlbscores(self, ctx):
        scores = get_mlb_scores()
        if not scores:
            await ctx.send("⚾ No MLB games found.")
            return

        message = "**TODAY'S MLB SCORES:**\n" + "\n".join(scores)
        await ctx.send(message)

async def setup(bot):
    await bot.add_cog(MLBScores(bot))