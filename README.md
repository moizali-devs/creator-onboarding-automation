# creator-onboarding-automation

Automation suite for creator onboarding and operations management. Built on Discord.py with modular workflow architecture.

## Current bot features

- Sends a branded welcome embed when a member joins the Discord server.
- Uses only the member intent and no background polling loops to keep server load low.
- Uses `WELCOME_CHANNEL_ID` when configured, otherwise falls back to the server system channel.

## Setup

1. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

2. Create your environment variables from `.env.example`.

3. Enable **Server Members Intent** for the bot in the Discord Developer Portal.

4. Start the bot:

   ```powershell
   python bot.py
   ```

## Environment variables

- `DISCORD_TOKEN`: Required Discord bot token.
- `WELCOME_CHANNEL_ID`: Optional target channel ID for welcome messages.
- `INTRODUCTIONS_CHANNEL_ID`: Optional channel ID for the introductions link.
- `GET_STARTED_CHANNEL_ID`: Optional channel ID for the onboarding link.
- `WELCOME_IMAGE_URL`: Optional direct image URL for the welcome banner.
