import random
from discord.ext import commands

class GuessGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def guess(self, ctx, number: int):
        if not 1 <= number <= 10:
            await ctx.send("Please guess a number between 1 and 10!")
            return

        correct = random.randint(1, 10)
        if number == correct:
            await ctx.send(f"🎉 You guessed it! It was {correct}.")
        else:
            await ctx.send(f"❌ Nope! I was thinking of {correct}.")

async def setup(bot):
    await bot.add_cog(GuessGame(bot))
