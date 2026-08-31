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
#: 서버 ID를 넣으면 그 서버에만 명령어를 등록한다. 전역 등록은 디스코드에 퍼지는 데
#: 최대 한 시간이 걸리지만, 서버 하나에 등록하면 즉시 보인다. 개발 중에는 이쪽이 낫다.
GUILD_ID = os.getenv("GUILD_ID")

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
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            logger.info("명령어 %d개를 서버 %s에 등록했습니다 (즉시 반영)", len(synced), GUILD_ID)
        else:
            synced = await bot.tree.sync()
            logger.info(
                "명령어 %d개를 전역 등록했습니다. 디스코드에 보이기까지 최대 한 시간이 "
                "걸립니다. 바로 쓰려면 .env에 GUILD_ID를 넣으세요.",
                len(synced),
            )
    except ValueError:
        logger.error("GUILD_ID가 숫자가 아닙니다: %r", GUILD_ID)
    except Exception:
        logger.exception("슬래시 명령어 등록 실패")


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
