# privacy_slash.py
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
from typing import Optional, Dict, Set
from datetime import datetime, timezone, timedelta

AUTO_DELETE_DELAY = 20  # seconds
MARK_REACTION = "⏳"
PRIVACY_MAP_FILE = "privacy_map.json"  # persisted mapping: { "<user_id>": [<channel_id>, ...], ... }
QUEUE_HISTORY_LIMIT = 200  # how many recent messages in that channel to scan when enabling

class PrivacyControl(commands.Cog):
    """
    PrivacyControl cog using slash commands.

    /privacy channel:<textchannel> enable:<bool>
      - enable=True -> enable privacy auto-delete for the calling user in that channel
      - enable=False -> disable privacy for that channel for the calling user

    /privacystatus
      - shows which channels you currently have privacy enabled in (ephemeral)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # user_id -> set(channel_id)
        self.privacy_map: Dict[int, Set[int]] = {}
        # queued message ids to avoid duplicates
        self._queued_ids: Set[int] = set()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker = self.bot.loop.create_task(self._worker_loop())
        self._load_privacy_map()

    def cog_unload(self):
        if not self._worker.cancelled():
            self._worker.cancel()
        # best-effort save
        try:
            self._save_privacy_map_sync()
        except Exception:
            pass

    # ---------- persistence ----------
    def _load_privacy_map(self):
        try:
            if os.path.exists(PRIVACY_MAP_FILE):
                with open(PRIVACY_MAP_FILE, "r") as f:
                    raw = json.load(f)
                self.privacy_map = {int(u): set(int(c) for c in chans) for u, chans in raw.items()}
                print(f"[PrivacyControl] Loaded privacy map for {len(self.privacy_map)} users.")
        except Exception as e:
            print(f"[PrivacyControl] Failed to load privacy map: {e}")

    async def _save_privacy_map(self):
        try:
            raw = {str(u): list(chs) for u, chs in self.privacy_map.items()}
            with open(PRIVACY_MAP_FILE, "w") as f:
                json.dump(raw, f)
        except Exception as e:
            print(f"[PrivacyControl] Failed to save privacy map: {e}")

    def _save_privacy_map_sync(self):
        raw = {str(u): list(chs) for u, chs in self.privacy_map.items()}
        with open(PRIVACY_MAP_FILE, "w") as f:
            json.dump(raw, f)

    # ---------- helper methods ----------
    def _is_privacy_enabled(self, user_id: int, channel_id: int) -> bool:
        return user_id in self.privacy_map and channel_id in self.privacy_map[user_id]

    def _enable_privacy(self, user_id: int, channel_id: int):
        self.privacy_map.setdefault(user_id, set()).add(channel_id)

    def _disable_privacy(self, user_id: int, channel_id: int):
        if user_id in self.privacy_map:
            self.privacy_map[user_id].discard(channel_id)
            if not self.privacy_map[user_id]:
                del self.privacy_map[user_id]

    # ---------- slash commands ----------
    @app_commands.command(name="privacy", description="Enable or disable privacy auto-delete in a channel for yourself.")
    @app_commands.describe(channel="Text channel where messages should be auto-deleted", enable="Enable (true) or disable (false) privacy in that channel")
    async def privacy(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        enable: Optional[bool] = True
    ):
        # ephemeral response to keep UI clean
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        user_id = user.id
        channel_id = channel.id

        # permission quick-check for the bot in that channel
        perms = channel.permissions_for(interaction.guild.me) if interaction.guild else None
        if perms is None or not (perms.view_channel and perms.read_message_history and perms.manage_messages):
            await interaction.followup.send(
                f"⚠️ I need **View Channel**, **Read Message History**, and **Manage Messages** in {channel.mention} to enable privacy there.",
                ephemeral=True
            )
            return

        if enable:
            if self._is_privacy_enabled(user_id, channel_id):
                await interaction.followup.send(f"✅ You already have privacy enabled in {channel.mention}.", ephemeral=True)
                return

            # enable
            self._enable_privacy(user_id, channel_id)
            await self._save_privacy_map()
            # queue recent messages from that channel for this user (global sweep limited to that channel)
            await self._queue_recent_messages_in_channel_for_user(channel, user_id)

            await interaction.followup.send(
                f"🔒 Privacy enabled in {channel.mention}. Your messages in that channel will be deleted after {AUTO_DELETE_DELAY} seconds.",
                ephemeral=True
            )
            print(f"[PrivacyControl] User {user} enabled privacy in {channel.guild}/{channel.name}")

        else:
            if not self._is_privacy_enabled(user_id, channel_id):
                await interaction.followup.send(f"ℹ️ You don't have privacy enabled in {channel.mention}.", ephemeral=True)
                return

            self._disable_privacy(user_id, channel_id)
            await self._save_privacy_map()
            await interaction.followup.send(f"🔓 Privacy disabled in {channel.mention}.", ephemeral=True)
            print(f"[PrivacyControl] User {user} disabled privacy in {channel.guild}/{channel.name}")

    @app_commands.command(name="privacystatus", description="Show which channels you have privacy auto-delete enabled in.")
    async def privacystatus(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        chans = self.privacy_map.get(user_id, set())
        if not chans:
            await interaction.followup.send("You have privacy disabled everywhere.", ephemeral=True)
            return

        # Build a friendly list of channel mentions that are still valid
        mentions = []
        for ch_id in chans:
            ch = self.bot.get_channel(ch_id)
            if ch:
                mentions.append(ch.mention)
            else:
                mentions.append(f"`#{ch_id}`")  # channel not in cache
        await interaction.followup.send("Privacy is enabled in: " + ", ".join(mentions), ephemeral=True)

    # ---------- message queueing ----------
    async def queue_message_for_deletion(self, message: discord.Message):
        """Queue a message for deletion after delay if it's not already queued."""
        if message.id in self._queued_ids:
            return
        # avoid queuing bot messages or commands
        if message.author.bot:
            return
        if message.content and message.content.startswith("!"):
            return

        # ensure privacy is enabled for that author in that channel
        if not self._is_privacy_enabled(message.author.id, message.channel.id):
            return

        self._queued_ids.add(message.id)
        await self._queue.put(message)
        # try to mark visually
        try:
            await message.add_reaction(MARK_REACTION)
        except Exception:
            pass
        # optional debug
        try:
            print(f"[PrivacyControl] Queued message {message.id} from {message.author} in {message.channel} for deletion")
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # only run in guild channels
        if message.guild is None:
            return
        # queue if appropriate
        await self.queue_message_for_deletion(message)

    async def _queue_recent_messages_in_channel_for_user(self, channel: discord.TextChannel, user_id: int):
        """
        Scan recent messages in the given channel only and queue those by user.
        This limits scanning to *one* channel (no global scans).
        """
        try:
            async for msg in channel.history(limit=QUEUE_HISTORY_LIMIT, oldest_first=False):
                if msg.author.id != user_id:
                    continue
                # avoid scanning extremely old messages if you prefer:
                # if msg.created_at < cutoff: break
                await self.queue_message_for_deletion(msg)
        except (discord.Forbidden, discord.HTTPException) as e:
            print(f"[PrivacyControl] Failed to scan {channel} for user {user_id}: {e}")

    # ---------- worker that deletes messages after delay ----------
    async def _worker_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                message: discord.Message = await self._queue.get()
                # simple delay
                await asyncio.sleep(AUTO_DELETE_DELAY)

                # double-check permission before attempting deletion
                try:
                    guild = message.guild
                    channel = message.channel
                except Exception:
                    guild = None
                    channel = None

                if guild and channel:
                    perms = channel.permissions_for(guild.me)
                    if not (perms.view_channel and perms.read_message_history and perms.manage_messages):
                        print(f"[PrivacyControl] Missing permissions to delete in {channel} (msg {message.id})")
                        self._queued_ids.discard(message.id)
                        continue

                # Only delete if privacy is still enabled for that user+channel (optional behavior)
                if not self._is_privacy_enabled(message.author.id, message.channel.id):
                    # user turned privacy off before deletion; skip deleting
                    print(f"[PrivacyControl] Skipping deletion of {message.id} because user disabled privacy")
                    self._queued_ids.discard(message.id)
                    continue

                try:
                    await message.delete()
                    print(f"[PrivacyControl] Deleted message {message.id} from {message.author} in {message.channel}")
                except discord.NotFound:
                    pass
                except discord.Forbidden as e:
                    print(f"[PrivacyControl] Forbidden deleting message {message.id}: {e}")
                except discord.HTTPException as e:
                    print(f"[PrivacyControl] HTTP error deleting message {message.id}: {e}")

                self._queued_ids.discard(message.id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[PrivacyControl] Worker error: {e}")
                await asyncio.sleep(2)

# ---------- setup ----------
async def setup(bot: commands.Bot):
    await bot.add_cog(PrivacyControl(bot))
    # optional: sync commands immediately (may be slow); normally not necessary every reload
    try:
        await bot.tree.sync()
    except Exception:
        # ignore sync failures here; tree will sync eventually
        pass