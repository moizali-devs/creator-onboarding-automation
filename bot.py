import logging
import os

import discord


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


WELCOME_CHANNEL_ID = os.getenv("WELCOME_CHANNEL_ID")
INTRODUCTIONS_CHANNEL_ID = os.getenv("INTRODUCTIONS_CHANNEL_ID")
GET_STARTED_CHANNEL_ID = os.getenv("GET_STARTED_CHANNEL_ID")
WELCOME_IMAGE_URL = os.getenv(
    "WELCOME_IMAGE_URL",
    "https://dummyimage.com/800x240/050607/8dfcff.png&text=WELCOME",
)


intents = discord.Intents.default()
intents.members = True


class CreatorOnboardingBot(discord.Client):
    async def on_ready(self) -> None:
        logging.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")

    async def on_member_join(self, member: discord.Member) -> None:
        channel = self._get_welcome_channel(member.guild)
        if channel is None:
            logging.warning("No welcome channel found for guild %s", member.guild.id)
            return

        introductions_channel = self._channel_reference(
            member.guild,
            INTRODUCTIONS_CHANNEL_ID,
            "introductions",
        )
        get_started_channel = self._channel_reference(
            member.guild,
            GET_STARTED_CHANNEL_ID,
            "lets-get-started",
        )

        embed = discord.Embed(
            title=f"{member.display_name} Welcome to the Rainbow Nutrients Affiliate Community",
            description=(
                f"{member.mention} We are excited to have you here.\n"
                "Welcome to the team behind the number one Hair Growth and Hair Care brand in the USA.\n\n"
                "Start by introducing yourself, then head to the onboarding channel to learn how to request "
                "your sample, explore content ideas, and access the tools to kick off your Rainbow Nutrients journey."
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
        if member.guild.icon:
            embed.set_thumbnail(url=member.guild.icon.url)
        embed.set_image(url=WELCOME_IMAGE_URL)
        embed.set_footer(text=f"Welcome to the server, {member.display_name}!")

        await channel.send(
            content=f"Welcome {member.mention} into the server",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

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
