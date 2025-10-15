import random
from typing import Optional
import discord
from discord import app_commands, Interaction
from discord.ext import commands

# Safety limits
MIN_SIDES = 2
MAX_SIDES = 1_000_000

class Roll(commands.Cog):
    """Slash command Cog for rolling dice: /roll sides:6 private:false"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="roll",
        description="Roll a die with the given number of sides (default: 6)."
    )
    @app_commands.describe(
        sides="Number of sides on the die (integer, min=2).",
        private="If true, the result is only visible to you (ephemeral)."
    )
    async def roll(
        self,
        interaction: Interaction,
        sides: Optional[int] = 6,
        private: Optional[bool] = False
    ):
        # Validate sides
        if sides is None:
            sides = 6

        if sides < MIN_SIDES or sides > MAX_SIDES:
            await interaction.response.send_message(
                f"❌ `sides` must be between {MIN_SIDES} and {MAX_SIDES}.",
                ephemeral=True
            )
            return

        # Perform roll
        try:
            result = random.randint(1, sides)
        except Exception as e:
            # Very defensive: in case randint fails (shouldn't), return an error
            await interaction.response.send_message(f"⚠️ Error rolling the die: {e}", ephemeral=True)
            return

        # Format message
        title = f"🎲 d{sides} roll"
        content = f"**{interaction.user.display_name}** rolled a **{result}** (1–{sides})"

        # Respond (ephemeral if requested)
        await interaction.response.send_message(f"{title}: {content}", ephemeral=bool(private))

async def setup(bot: commands.Bot):
    await bot.add_cog(Roll(bot))