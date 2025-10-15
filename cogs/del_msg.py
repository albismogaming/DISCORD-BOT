import discord
from discord import app_commands, Interaction
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from typing import Optional, List

SCAN_LIMIT = 50  # Limit messages scanned per channel
MAX_AMOUNT = 100  # Safety cap for amount-mode

class MessageCleanup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="poof",
        description="Delete your own messages in a specific channel"
    )
    @app_commands.describe(
        channel="The channel to delete messages from (defaults to current channel)",
        amount="Number of messages to delete (default 100)",
        timeframe="Time window (e.g., 10m = 10 minutes, 2h = 2 hours)"
    )
    async def poof(
        self,
        interaction: Interaction,
        channel: Optional[discord.TextChannel] = None,
        amount: Optional[int] = None,
        timeframe: Optional[str] = None
    ):
        target_channel = channel or interaction.channel
        author = interaction.user
        after_time: Optional[datetime] = None

        # --- parse timeframe ---
        if timeframe:
            if len(timeframe) < 2 or not timeframe[:-1].isdigit() or timeframe[-1].lower() not in ("m", "h"):
                return await interaction.response.send_message(
                    "❌ Invalid timeframe format. Use 10m for 10 minutes or 2h for 2 hours.",
                    ephemeral=True
                )
            value = int(timeframe[:-1])
            after_time = datetime.now(timezone.utc) - (
                timedelta(minutes=value) if timeframe[-1].lower() == "m" else timedelta(hours=value)
            )

        if amount is not None and (amount <= 0 or amount > MAX_AMOUNT):
            return await interaction.response.send_message(
                f"❌ Amount must be between 1 and {MAX_AMOUNT}.",
                ephemeral=True
            )

        if amount is None and after_time is None:
            amount = 100

        perms = target_channel.permissions_for(interaction.guild.me)
        if not perms.manage_messages or not perms.read_message_history:
            return await interaction.response.send_message(
                f"🚫 I need **Read Message History** and **Manage Messages** in {target_channel.mention}.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)  # Show thinking...

        deleted_count = 0
        to_delete: List[discord.Message] = []

        try:
            # Scan only the target channel
            async for msg in target_channel.history(limit=SCAN_LIMIT, oldest_first=False):
                if msg.author != author:
                    continue
                if after_time and msg.created_at < after_time:
                    break
                to_delete.append(msg)
                if amount and len(to_delete) >= amount:
                    break

            if not to_delete:
                return await interaction.followup.send(
                    f"ℹ️ No messages found to delete in {target_channel.mention}.",
                    ephemeral=True
                )

            # Bulk-delete messages younger than 14 days
            while to_delete:
                chunk = [m for m in to_delete[:100] if (datetime.now(timezone.utc) - m.created_at).days < 14]
                if chunk:
                    await target_channel.delete_messages(chunk)
                    deleted_count += len(chunk)

                # Delete older messages individually
                for m in to_delete[:100]:
                    if (datetime.now(timezone.utc) - m.created_at).days >= 14:
                        try:
                            await m.delete()
                            deleted_count += 1
                        except Exception:
                            pass

                to_delete = to_delete[100:]

        except discord.Forbidden:
            return await interaction.followup.send(f"🚫 I lack permission to delete messages in {target_channel.mention}.", ephemeral=True)
        except discord.HTTPException as e:
            return await interaction.followup.send(f"⚠️ Failed to delete messages: {e}", ephemeral=True)

        # --- humanized time info ---
        time_info = ""
        if after_time:
            delta = datetime.now(timezone.utc) - after_time
            mins = int(delta.total_seconds() // 60)
            if mins < 60:
                time_info = f" in last {mins}m"
            else:
                hrs = round(mins / 60, 1)
                time_info = f" in last {hrs}h"

        await interaction.followup.send(
            f"💨 **Poof!** Deleted {deleted_count} of your messages{time_info} in {target_channel.mention}.",
            ephemeral=True
        )

# --- setup ---
async def setup(bot: commands.Bot):
    await bot.add_cog(MessageCleanup(bot))
