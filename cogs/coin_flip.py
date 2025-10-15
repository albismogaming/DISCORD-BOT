import random
import asyncio
from discord import app_commands, Interaction
from discord.ext import commands

class CoinFlip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="coinflip", description="Flips a coin resulting in heads or tails")
    async def flip(self, interaction: Interaction):
        outcome = random.choice(["Heads 🪙", "Tails 🪙"])

        # Send response to the slash command
        await interaction.response.send_message(f"The coin landed on... **{outcome}**!")

        # Grab the sent message
        message = await interaction.original_response()

        # Delete it after 10 seconds
        await asyncio.sleep(10)
        try:
            await message.delete()
        except:
            pass  # ignore if already deleted or missing permissions

async def setup(bot: commands.Bot):
    await bot.add_cog(CoinFlip(bot))