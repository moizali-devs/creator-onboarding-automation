import logging
import os
from pathlib import Path

import discord
from discord import app_commands
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


intents = discord.Intents.default()
intents.members = True


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

        embed = discord.Embed(
            title=f"{member.display_name} Welcome to the PetLab Co. Creator Community",
            description=(
                f"{member.mention} We are excited to have you here.\n"
                "Welcome to the creator community behind PetLab Co., focused on helping pet parents discover trusted "
                "products for their dogs.\n\n"
                "Start by introducing yourself, then head to the onboarding channel to learn how to request your "
                "sample, explore content ideas, and access the resources you need to get started with PetLab Co."
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
