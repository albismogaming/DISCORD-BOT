# cogs/rps_interactive.py
import random
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

CHOICES = ["rock", "paper", "scissors"]
CHOICE_EMOJI = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}

def determine_winner(user: str, bot: str) -> str:
    """Return 'win', 'lose', or 'draw'"""
    if user == bot:
        return "draw"
    if (user == "rock" and bot == "scissors") or \
       (user == "paper" and bot == "rock") or \
       (user == "scissors" and bot == "paper"):
        return "win"
    return "lose"

class RPSView(discord.ui.View):
    def __init__(self, author_id: int, best_of: int, *, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.best_of = best_of
        self.to_win = best_of // 2 + 1
        self.user_score = 0
        self.bot_score = 0
        self.round_num = 1
        self.history: List[str] = []  # lines describing each round
        self.message: discord.Message | None = None

    def _build_status_embed(self) -> discord.Embed:
        title = f"Rock · Paper · Scissors — Best of {self.best_of}"
        embed = discord.Embed(title=title, color=discord.Color.blurple())
        embed.add_field(name="Score", value=f"You: **{self.user_score}** — Bot: **{self.bot_score}**", inline=False)
        embed.add_field(name="Rounds played", value=str(self.round_num - 1) or "0", inline=False)
        if self.history:
            # show last 6 rounds for brevity
            embed.add_field(name="Recent rounds", value="\n".join(self.history[-6:]), inline=False)
        embed.set_footer(text="Click a button to play the next round. Game will timeout after 60s of inactivity.")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the invoking user may use the buttons."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the user who started this game may press the buttons.", ephemeral=True)
            return False
        return True

    async def end_game(self, interaction: discord.Interaction, final_message: str):
        """Disable buttons and edit final message."""
        for child in self.children:
            child.disabled = True
        embed = self._build_status_embed()
        embed.add_field(name="Result", value=final_message, inline=False)
        # Edit the original message to show final state and disable buttons
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            # fallback if interaction already responded
            if self.message:
                await self.message.edit(embed=embed, view=self)

    async def continue_round(self, interaction: discord.Interaction, user_choice: str):
        """Run a single round with the provided user_choice and update message."""
        bot_choice = random.choice(CHOICES)
        result = determine_winner(user_choice, bot_choice)

        emoji_user = CHOICE_EMOJI.get(user_choice, user_choice)
        emoji_bot = CHOICE_EMOJI.get(bot_choice, bot_choice)
        if result == "win":
            self.user_score += 1
            desc = f"R{self.round_num}: {emoji_user} **{user_choice.capitalize()}** vs {emoji_bot} **{bot_choice.capitalize()}** → **You win** this round!"
        elif result == "lose":
            self.bot_score += 1
            desc = f"R{self.round_num}: {emoji_user} **{user_choice.capitalize()}** vs {emoji_bot} **{bot_choice.capitalize()}** → **Bot wins** this round!"
        else:
            desc = f"R{self.round_num}: {emoji_user} **{user_choice.capitalize()}** vs {emoji_bot} **{bot_choice.capitalize()}** → **Draw**."

        self.history.append(desc)
        self.round_num += 1

        # Check for series end
        if self.user_score >= self.to_win or self.bot_score >= self.to_win:
            winner = "You" if self.user_score > self.bot_score else "The Bot"
            final_message = f"{winner} won the series! Final score — You: **{self.user_score}**, Bot: **{self.bot_score}**"
            await self.end_game(interaction, final_message)
            return

        # still playing: update embed and keep buttons enabled
        embed = self._build_status_embed()
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            # fallback when interaction already responded
            if self.message:
                await self.message.edit(embed=embed, view=self)

    # Buttons
    @discord.ui.button(label="Rock", style=discord.ButtonStyle.secondary, emoji="🪨")
    async def rock_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.continue_round(interaction, "rock")

    @discord.ui.button(label="Paper", style=discord.ButtonStyle.secondary, emoji="📄")
    async def paper_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.continue_round(interaction, "paper")

    @discord.ui.button(label="Scissors", style=discord.ButtonStyle.secondary, emoji="✂️")
    async def scissors_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.continue_round(interaction, "scissors")

    async def on_timeout(self):
        # disable buttons on timeout
        for c in self.children:
            c.disabled = True
        # edit the message to show timeout state if possible
        embed = self._build_status_embed()
        embed.add_field(name="Timeout", value="Game timed out due to inactivity.", inline=False)
        try:
            if self.message:
                await self.message.edit(embed=embed, view=self)
        except Exception:
            pass

class RockPaperScissors(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rockpaperscissors", description="Play Rock Paper Scissors interactively (best-of selector + buttons).")
    @app_commands.describe(
        best_of="Choose the series length (best of 1,3,5,7)."
    )
    @app_commands.choices(
        best_of=[
            app_commands.Choice(name="Best of 1", value=1),
            app_commands.Choice(name="Best of 3", value=3),
            app_commands.Choice(name="Best of 5", value=5),
            app_commands.Choice(name="Best of 7", value=7),
        ]
    )
    async def rps(self, interaction: discord.Interaction, best_of: app_commands.Choice[int]):
        rounds = best_of.value
        view = RPSView(interaction.user.id, rounds, timeout=60.0)

        embed = view._build_status_embed()
        msg = await interaction.response.send_message(embed=embed, view=view)
        # store message on the view so the view callbacks can edit it if needed
        # on some discord.py versions interaction.response.send_message returns None,
        # so we fetch the message from the channel instead.
        try:
            view.message = await msg.original_response()
        except Exception:
            # fallback: fetch last message in channel by the bot/user — best-effort
            try:
                async for m in interaction.channel.history(limit=10):
                    if m.author == self.bot.user and m.components:
                        view.message = m
                        break
            except Exception:
                view.message = None

# setup
async def setup(bot: commands.Bot):
    await bot.add_cog(RockPaperScissors(bot))
