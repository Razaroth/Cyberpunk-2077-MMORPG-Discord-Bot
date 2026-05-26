"""
bot.py — Night City MMORPG Discord Bot entry point
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import discord
from discord.ext import commands

import config
from database.db import Database

# ─────────────────────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("NightCity")

# ─────────────────────────────────────────────────────────────
#  Cogs to Load
# ─────────────────────────────────────────────────────────────
COGS = [
    "cogs.character",
    "cogs.combat",
    "cogs.exploration",
    "cogs.inventory",
    "cogs.economy",
    "cogs.missions",
    "cogs.cyberware",
    "cogs.skills",
    "cogs.factions",
    "cogs.social",
    "cogs.admin",
]


# ─────────────────────────────────────────────────────────────
#  Bot Class
# ─────────────────────────────────────────────────────────────
class NightCityBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()

        guild_id = config.GUILD_ID
        if guild_id:
            kwargs = {}
        else:
            kwargs = {}

        super().__init__(
            command_prefix=config.BOT_PREFIX,
            intents=intents,
            application_id=config.APPLICATION_ID,
            **kwargs,
        )
        self.db = Database(config.DATABASE_PATH)

    async def setup_hook(self):
        log.info("Initializing database...")
        await self.db.initialize()

        log.info("Loading cogs...")
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info(f"  ✓ Loaded {cog}")
            except Exception as e:
                log.error(f"  ✗ Failed to load {cog}: {e}", exc_info=True)

        # Sync slash commands
        guild_id = config.GUILD_ID
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info(f"Synced {len(synced)} commands to guild {guild_id}.")
        else:
            synced = await self.tree.sync()
            log.info(f"Synced {len(synced)} global commands.")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="Cyberpunk 2077 | /start"
            )
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ):
        from utils.embeds import error_embed
        if isinstance(error, discord.app_commands.MissingPermissions):
            msg = "You don't have permission to use this command."
        elif isinstance(error, discord.app_commands.CommandOnCooldown):
            msg = f"This command is on cooldown. Try again in {error.retry_after:.1f}s."
        elif isinstance(error, discord.app_commands.CheckFailure):
            msg = "You don't meet the requirements to use this command."
        else:
            log.error(f"Unhandled app command error: {error}", exc_info=True)
            msg = "An unexpected error occurred. The devs have been notified."

        embed = error_embed("Command Error", msg)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            pass

    async def close(self):
        log.info("Shutting down — closing database connection...")
        await self.db.close()
        await super().close()


# ─────────────────────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────────────────────
async def main():
    token = config.BOT_TOKEN
    if not token:
        log.critical("BOT_TOKEN is not set! Add it to your .env file.")
        sys.exit(1)

    bot = NightCityBot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
