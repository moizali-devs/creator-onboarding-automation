import logging
import os
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


WELCOME_CHANNEL_ID = os.getenv("WELCOME_CHANNEL_ID")
INTRODUCTIONS_CHANNEL_ID = os.getenv("INTRODUCTIONS_CHANNEL_ID")
GET_STARTED_CHANNEL_ID = os.getenv("GET_STARTED_CHANNEL_ID")
BOT_LOG_CHANNEL_ID = os.getenv("BOT_LOG_CHANNEL_ID")
WELCOME_IMAGE_URL = os.getenv(
    "WELCOME_IMAGE_URL",
    "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExcXlobmRxbzZkNTZ1Z2g0b2l1Y3ZkdXdpYnpybDRxeDA0NTB4OHlteiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3oKIPsx2VAYAgEHC12/giphy.gif",
)

ROAD_TO_RETAINER_CHANNEL_ID = "1508891637365866517"

EUKA_STORE_ID = os.getenv("EUKA_STORE_ID")
LEADERBOARD_CHANNEL_ID = os.getenv("LEADERBOARD_CHANNEL_ID")
LEADERBOARD_TOP_N = int(os.getenv("LEADERBOARD_TOP_N", "10"))

EUKA_API_BASE = "https://app.euka.ai/api"

# Medal emojis for top 3, numbers for the rest
RANK_ICONS = {1: "🥇", 2: "🥈", 3: "🥉"}


intents = discord.Intents.default()
intents.members = True


def _find_gmv_field(record: dict) -> tuple[str, float] | tuple[None, None]:
    """Return (field_name, value) for the best GMV-like field in a creator record.

    Prefers shop-specific GMV (e.g. last_30d_gmv_our_shop) over cross-brand totals.
    """
    gmv_keys = [k for k in record if "gmv" in k.lower()]
    # Prefer the shop-scoped field if present
    preferred = [k for k in gmv_keys if k.lower().endswith("_our_shop")]
    for key in (preferred or gmv_keys):
        try:
            return key, float(record[key] or 0)
        except (TypeError, ValueError):
            continue
    return None, None


def _gmv_sort_key(record: dict) -> float:
    _, value = _find_gmv_field(record)
    return value or 0.0


async def fetch_creator_leaderboard() -> list[dict]:
    """Fetch creator_level data from the Euka API and return sorted by GMV desc."""
    if not EUKA_STORE_ID:
        raise RuntimeError("EUKA_STORE_ID is not set.")

    url = f"{EUKA_API_BASE}/data-export"
    params = {"type": "creator_level", "store_id": EUKA_STORE_ID, "export_type": "json"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=300)) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Euka API returned {resp.status}: {text[:200]}")
            payload = await resp.json()

    creators: list[dict] = payload.get("data", [])
    creators.sort(key=_gmv_sort_key, reverse=True)
    return creators


def build_leaderboard_embed(creators: list[dict], top_n: int) -> discord.Embed:
    from datetime import datetime, timezone
    embed = discord.Embed(
        title="🏆  Creator Leaderboard",
        color=discord.Color.from_rgb(255, 151, 42),
    )

    top = creators[:top_n]
    if not top:
        embed.description = "No creator data available."
        return embed

    # Detect the GMV field name from the first record
    gmv_field, _ = _find_gmv_field(top[0])

    lines = []
    for rank, creator in enumerate(top, start=1):
        icon = RANK_ICONS.get(rank, f"`{rank}.`")
        handle = creator.get("creator_handle") or creator.get("handle") or "Unknown"
        gmv_raw = creator.get(gmv_field) if gmv_field else None
        try:
            gmv = float(gmv_raw or 0)
            gmv_str = f"${gmv:,.2f}"
        except (TypeError, ValueError):
            gmv_str = "N/A"

        lines.append(f"{icon}  **@{handle}**\n\u200b    └ GMV: **{gmv_str}**")

    embed.description = "\n".join(lines)
    embed.set_footer(text=f"Top {top_n} creators by GMV  •  Updates every 24 hours")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


class CreatorOnboardingBot(discord.Client):
    def __init__(self, *, intents: discord.Intents, member_cache_flags: discord.MemberCacheFlags) -> None:
        super().__init__(intents=intents, member_cache_flags=member_cache_flags)
        self.tree = app_commands.CommandTree(self)
        self._synced = False

    async def on_ready(self) -> None:
        logging.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")
        if not self._synced:
            await self.tree.sync()
            self._synced = True
            logging.info("Application commands synced")

        if EUKA_STORE_ID and LEADERBOARD_CHANNEL_ID:
            if not self.daily_leaderboard.is_running():
                self.daily_leaderboard.start()
                logging.info("Daily leaderboard task started")
        else:
            logging.warning("EUKA_STORE_ID or LEADERBOARD_CHANNEL_ID not set — leaderboard disabled")

    @tasks.loop(hours=24)
    async def daily_leaderboard(self) -> None:
        await self._post_leaderboard_to_channel()

    @daily_leaderboard.before_loop
    async def before_daily_leaderboard(self) -> None:
        await self.wait_until_ready()

    async def _post_leaderboard_to_channel(self) -> None:
        if not LEADERBOARD_CHANNEL_ID:
            return

        # Find the channel across all guilds
        channel_id = int(LEADERBOARD_CHANNEL_ID)
        channel = self.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logging.warning("Leaderboard channel %s not found or not a text channel", LEADERBOARD_CHANNEL_ID)
            return

        try:
            creators = await fetch_creator_leaderboard()
            embed = build_leaderboard_embed(creators, LEADERBOARD_TOP_N)
            await channel.send(embed=embed)
            logging.info("Leaderboard posted to channel %s (%d creators)", LEADERBOARD_CHANNEL_ID, len(creators))
        except Exception as exc:
            logging.error("Failed to post leaderboard: %s", exc)
            await self._send_log_message(
                channel.guild,
                title="Leaderboard Post Failed",
                description=f"Could not post the daily leaderboard: {exc}",
                color=discord.Color.red(),
            )

    async def on_member_join(self, member: discord.Member) -> None:
        channel = self._get_welcome_channel(member.guild)
        if channel is None:
            logging.warning("No welcome channel found for guild %s", member.guild.id)
            await self._send_log_message(
                member.guild,
                title="Welcome Send Failed",
                description=f"Could not find a welcome channel for {member.mention}.",
                color=discord.Color.red(),
            )
            return

        await self._send_welcome_message(channel, member)
        await self._send_log_message(
            member.guild,
            title="Member Joined",
            description=f"Sent welcome message for {member.mention} in {channel.mention}.",
            color=discord.Color.green(),
        )

    async def setup_hook(self) -> None:
        @self.tree.command(name="preview_welcome", description="Preview the welcome message for a member.")
        @app_commands.checks.has_permissions(manage_guild=True)
        @app_commands.describe(
            member="Member to preview the welcome message for.",
            channel="Channel where the preview should be sent.",
        )
        async def preview_welcome(
            interaction: discord.Interaction,
            member: discord.Member | None = None,
            channel: discord.TextChannel | None = None,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "Run this command in a server.",
                    ephemeral=True,
                )
                return

            target_member = member or interaction.user
            target_channel = channel or interaction.channel
            if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
                await interaction.response.send_message(
                    "Choose a server text channel or thread for the preview.",
                    ephemeral=True,
                )
                return

            await self._send_welcome_message(target_channel, target_member)
            await interaction.response.send_message(
                f"Welcome preview for {target_member.mention} sent to {target_channel.mention}.",
                ephemeral=True,
            )
            await self._send_log_message(
                interaction.guild,
                title="Welcome Preview Sent",
                description=(
                    f"{interaction.user.mention} previewed the welcome message for {target_member.mention} "
                    f"in {target_channel.mention}."
                ),
                color=discord.Color.blurple(),
            )

        @self.tree.command(name="leaderboard", description="Post the current creator leaderboard.")
        @app_commands.checks.has_permissions(manage_guild=True)
        @app_commands.describe(channel="Channel to post the leaderboard in (defaults to current channel).")
        async def leaderboard(
            interaction: discord.Interaction,
            channel: discord.TextChannel | None = None,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Run this command in a server.", ephemeral=True)
                return

            if not EUKA_STORE_ID:
                await interaction.response.send_message(
                    "EUKA_STORE_ID is not configured on this bot.", ephemeral=True
                )
                return

            target_channel = channel or interaction.channel
            if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
                await interaction.response.send_message(
                    "Choose a server text channel or thread.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            try:
                creators = await fetch_creator_leaderboard()
                embed = build_leaderboard_embed(creators, LEADERBOARD_TOP_N)
                await target_channel.send(embed=embed)
                await interaction.followup.send(
                    f"Leaderboard posted to {target_channel.mention}.", ephemeral=True
                )
                await self._send_log_message(
                    interaction.guild,
                    title="Leaderboard Posted",
                    description=(
                        f"{interaction.user.mention} manually posted the creator leaderboard "
                        f"in {target_channel.mention}."
                    ),
                    color=discord.Color.blurple(),
                )
            except Exception as exc:
                logging.error("Leaderboard command failed: %s", exc)
                await interaction.followup.send(
                    f"Failed to fetch leaderboard data: {exc}", ephemeral=True
                )

    async def _send_welcome_message(
        self,
        channel: discord.TextChannel | discord.Thread,
        member: discord.abc.User,
    ) -> None:
        guild = channel.guild

        introductions_channel = self._channel_reference(
            guild,
            INTRODUCTIONS_CHANNEL_ID,
            "introductions",
        )
        get_started_channel = self._channel_reference(
            guild,
            GET_STARTED_CHANNEL_ID,
            "lets-get-started",
        )
        road_to_retainer_channel = self._channel_reference(
            guild,
            ROAD_TO_RETAINER_CHANNEL_ID,
            "road-to-retainer",
        )

        embed = discord.Embed(
            title=f"{member.display_name} Welcome to the PetLab Co. Creator Community",
            description=(
                f"{member.mention} We are excited to have you here.\n"
                "Welcome to the creator community behind PetLab Co., focused on helping pet parents discover trusted "
                "products for their dogs.\n\n"
                "Start by introducing yourself, then head to the onboarding channel to learn how to request your "
                "sample, explore content ideas, and access the resources you need to get started with PetLab Co.\n\n"
                "**We have a huge opportunity for affiliates to land a retainer with PetLab Co.** — "
                "top-performing creators can move from affiliate to a paid retainer partnership."
            ),
            color=discord.Color.from_rgb(255, 151, 42),
        )
        embed.add_field(
            name="Introduce Yourself",
            value=f"Say hello in {introductions_channel} so the team can meet you.",
            inline=False,
        )
        embed.add_field(
            name="Get Started",
            value=(
                f"Head over to {get_started_channel} to learn how to request your sample "
                "and access the onboarding resources."
            ),
            inline=False,
        )
        embed.add_field(
            name="Road to Retainer",
            value=f"Head to {road_to_retainer_channel} to find out what it takes to land a paid retainer with PetLab Co.",
            inline=False,
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_image(url=WELCOME_IMAGE_URL)
        embed.set_footer(text=f"Welcome to the server, {member.display_name}!")

        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    async def _send_log_message(
        self,
        guild: discord.Guild,
        *,
        title: str,
        description: str,
        color: discord.Color,
    ) -> None:
        if not BOT_LOG_CHANNEL_ID:
            return

        log_channel = self._get_channel_by_id(guild, BOT_LOG_CHANNEL_ID)
        if not isinstance(log_channel, (discord.TextChannel, discord.Thread)):
            logging.warning("Invalid log channel for guild %s", guild.id)
            return

        embed = discord.Embed(title=title, description=description, color=color)
        await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    def _get_welcome_channel(self, guild: discord.Guild) -> discord.TextChannel | discord.Thread | None:
        if WELCOME_CHANNEL_ID:
            channel = self._get_channel_by_id(guild, WELCOME_CHANNEL_ID)
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                return channel

        bot_member = guild.me
        if bot_member is None:
            return None

        if guild.system_channel:
            permissions = guild.system_channel.permissions_for(bot_member)
            if permissions.send_messages and permissions.embed_links:
                return guild.system_channel

        for channel in guild.text_channels:
            permissions = channel.permissions_for(bot_member)
            if permissions.send_messages and permissions.embed_links:
                return channel

        return None

    def _channel_reference(self, guild: discord.Guild, channel_id: str | None, fallback_name: str) -> str:
        if channel_id:
            channel = self._get_channel_by_id(guild, channel_id)
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                return channel.mention

        return f"#{fallback_name}"

    def _get_channel_by_id(
        self,
        guild: discord.Guild,
        channel_id: str,
    ) -> discord.abc.GuildChannel | discord.Thread | None:
        try:
            channel_id_int = int(channel_id)
        except ValueError:
            logging.warning("Invalid channel ID: %s", channel_id)
            return None

        return guild.get_channel(channel_id_int)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set DISCORD_TOKEN before starting the bot.")

    client = CreatorOnboardingBot(
        intents=intents,
        member_cache_flags=discord.MemberCacheFlags.none(),
    )
    client.run(token, log_handler=None)


if __name__ == "__main__":
    main()
