import asyncio
import logging
import os

import discord
from discord import app_commands
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


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    """명령어에서 터진 예외를 콘솔과 디스코드 양쪽에 남긴다.

    이게 없으면 디스코드에는 "애플리케이션이 응답하지 않았어요"만 뜨고
    무엇이 왜 실패했는지 알 수 없다.
    """
    command = interaction.command.name if interaction.command else "?"
    logger.exception("'/%s' 실행 실패", command, exc_info=error)

    if isinstance(error, app_commands.MissingPermissions):
        text = bot.persona.line("no_permission")
    elif isinstance(error, app_commands.NoPrivateMessage):
        text = bot.persona.line("guild_only")
    else:
        text = f"{bot.persona.line('error')}\n`{type(error).__name__}: {error}`"

    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        logger.exception("오류 안내 메시지 전송 실패")


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
