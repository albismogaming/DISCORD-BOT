import random
import discord
from discord.ext import commands

class DiceBattle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def dicebattle(self, ctx, opponent: discord.Member):
        if opponent.bot:
            await ctx.send("🤖 You can't battle a bot!")
            return
        if opponent == ctx.author:
            await ctx.send("🪞 You can't battle yourself!")
            return

        await ctx.send(f"🎲 {ctx.author.mention} challenges {opponent.mention} to a dice battle!")

        p1_roll = random.randint(1, 6)
        p2_roll = random.randint(1, 6)

        await ctx.send(f"🔹 {ctx.author.display_name} rolls... **{p1_roll}**!")
        await ctx.send(f"🔸 {opponent.display_name} rolls... **{p2_roll}**!")

        if p1_roll > p2_roll:
            await ctx.send(f"🏆 {ctx.author.mention} wins the battle!")
        elif p2_roll > p1_roll:
            await ctx.send(f"🏆 {opponent.mention} wins the battle!")
        else:
            await ctx.send("⚔️ It's a tie! Rematch?")

async def setup(bot):
    await bot.add_cog(DiceBattle(bot))
