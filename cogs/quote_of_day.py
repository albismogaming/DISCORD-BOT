import aiohttp
from discord import app_commands, Interaction
from discord.ext import commands

QUOTE_API_URL = "https://api.quotable.io/random"

class QuoteOfTheDay(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="quote",
        description="Get a random quote or submit your own!"
    )
    @app_commands.describe(
        mode="Choose between getting a random quote or submitting your own",
        text="The quote text (if submitting your own)",
        author="The author of the quote (optional if submitting your own)",
        tags="Comma-separated tags to filter random quotes"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Random Quote", value="random"),
        app_commands.Choice(name="Submit Your Own", value="submit")
    ])
    async def quote(self, interaction: Interaction, mode: app_commands.Choice[str], text: str = None, author: str = None, tags: str = None):
        await interaction.response.defer()

        if mode.value == "submit":
            if not text:
                return await interaction.followup.send("Please provide the text of your quote.", ephemeral=True)
            author_str = f"— *{author}*" if author else "— *Unknown*"
            await interaction.followup.send(f"💡 **Quote:**\n\n\"{text}\"\n{author_str}")
            return

        # Random quote mode
        params = {}
        if tags:
            tags_formatted = ",".join(tag.strip().lower() for tag in tags.split(","))
            params["tags"] = tags_formatted

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(QUOTE_API_URL, params=params) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
        except Exception as e:
            return await interaction.followup.send(f"Failed to fetch a quote: {e}", ephemeral=True)

        quote_text = data.get("content", "No quote found.")
        quote_author = data.get("author", "Unknown")
        await interaction.followup.send(f"💡 **Quote:**\n\n\"{quote_text}\"\n— *{quote_author}*")

async def setup(bot: commands.Bot):
    await bot.add_cog(QuoteOfTheDay(bot))
