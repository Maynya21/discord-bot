import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from personas import load_persona

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PERSONA_KEY = os.getenv("PERSONA", "chara")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.persona = load_persona(PERSONA_KEY)


@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    logger.info("Persona: %s (%s)", bot.persona.name, bot.persona.key)
    try:
        synced = await bot.tree.sync()
        logger.info("Synced %d slash command(s)", len(synced))
    except Exception:
        logger.exception("Failed to sync slash commands")


async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("_"):
            await bot.load_extension(f"cogs.{filename[:-3]}")


async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Check your .env file.")
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
