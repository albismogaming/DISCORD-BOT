import random
from discord.ext import commands

class Roll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def roll(self, ctx, dice: str = "d6"):
        try:
            sides = int(dice.lower().replace("d", ""))
            result = random.randint(1, sides)
            await ctx.send(f"🎲 YOU ROLLED A **{result}** ON A {sides}-SIDED DIE!")
        except ValueError:
            await ctx.send("❌ Invalid format. Use `!roll d6`, `!roll d20`, etc.")

# 👇 MUST be async now
async def setup(bot):
    await bot.add_cog(Roll(bot))  # 👈 also MUST be awaited

