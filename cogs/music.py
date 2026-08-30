"""음성 채널에서 음악을 재생한다.

소리는 유튜브에서 가져온다. 스포티파이는 오디오를 주지 않으므로 '무엇을 틀지'만
담당한다 — 스포티파이 링크를 받으면 곡 이름 목록으로 풀고, 각 곡을 유튜브에서
찾아 재생한다.

재생 목록은 서버마다 따로 돌아간다. 각 서버의 Player가 대기열을 하나 들고,
백그라운드 작업이 한 곡씩 꺼내 재생한다. 아무것도 들어오지 않은 채 IDLE_TIMEOUT이
지나면 스스로 나간다.
"""

import asyncio
import logging
import os
from collections import deque
from typing import NamedTuple

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

from spotify import Spotify, SpotifyError, parse_link

logger = logging.getLogger("bot.music")

#: 대기열이 빈 채로 이만큼 지나면 음성 채널에서 나간다(초).
IDLE_TIMEOUT = 300
#: 스포티파이 링크 하나에서 가져올 곡 수 상한.
PLAYLIST_LIMIT = 100
#: /queue로 보여줄 곡 수.
QUEUE_PREVIEW = 10

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "extract_flat": False,
}
FFMPEG_OPTS = {
    # 스트림이 끊기면 다시 붙는다. 없으면 긴 곡 중간에 조용히 멈춘다.
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class Track(NamedTuple):
    #: 유튜브에서 찾을 검색어 또는 URL. 재생 직전에 푼다.
    query: str
    #: 표시용 이름. 스포티파이에서 온 곡은 아직 유튜브를 안 뒤진 상태다.
    title: str
    requester: str


def extract(query: str) -> dict:
    """yt-dlp로 스트림 정보를 얻는다. 블로킹 호출이라 스레드에서 부른다."""
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
    # 검색이면 결과 목록으로 온다.
    if "entries" in info:
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise yt_dlp.utils.DownloadError("결과 없음")
        info = entries[0]
    return info


class Player:
    """서버 한 곳의 대기열과 재생 루프."""

    def __init__(self, cog: "Music", guild: discord.Guild, channel: discord.abc.Messageable):
        self.cog = cog
        self.guild = guild
        self.channel = channel
        # asyncio.Queue 대신 deque를 쓴다. /queue가 남은 곡을 들여다봐야 하는데
        # Queue는 그 방법을 공개하지 않는다.
        self.pending: deque[Track] = deque()
        self.added = asyncio.Event()
        self.advance = asyncio.Event()
        self.current: Track | None = None
        self.task = cog.bot.loop.create_task(self.run())

    def say(self, key: str, **kwargs) -> str:
        return self.cog.bot.persona.line(key, **kwargs)

    async def run(self):
        while True:
            self.advance.clear()
            while not self.pending:
                self.added.clear()
                try:
                    await asyncio.wait_for(self.added.wait(), timeout=IDLE_TIMEOUT)
                except asyncio.TimeoutError:
                    await self.disconnect()
                    return
            track = self.pending.popleft()

            try:
                info = await asyncio.to_thread(extract, track.query)
            except Exception:
                logger.exception("'%s' 를 찾지 못했다", track.query)
                await self.send(self.say("music_not_found", query=track.title))
                continue

            source = discord.FFmpegOpusAudio(info["url"], **FFMPEG_OPTS)
            self.current = track._replace(title=info.get("title") or track.title)

            voice = self.guild.voice_client
            if voice is None or not voice.is_connected():
                return
            voice.play(source, after=self._finished)
            await self.send(self.say("music_now", title=self.current.title))

            await self.advance.wait()
            self.current = None

    def _finished(self, error: Exception | None):
        if error:
            logger.error("재생 중 오류: %s", error)
        self.cog.bot.loop.call_soon_threadsafe(self.advance.set)

    async def send(self, text: str):
        try:
            await self.channel.send(text)
        except discord.HTTPException:
            logger.exception("메시지 전송 실패")

    async def disconnect(self):
        voice = self.guild.voice_client
        if voice:
            await voice.disconnect()
        self.cog.players.pop(self.guild.id, None)

    def add(self, track: Track):
        self.pending.append(track)
        self.added.set()

    def stop(self):
        self.task.cancel()
        self.pending.clear()


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, Player] = {}
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.spotify = Spotify(client_id, secret) if client_id and secret else None

    def player_for(self, interaction: discord.Interaction) -> Player:
        player = self.players.get(interaction.guild.id)
        if player is None or player.task.done():
            player = Player(self, interaction.guild, interaction.channel)
            self.players[interaction.guild.id] = player
        player.channel = interaction.channel
        return player

    async def join(self, interaction: discord.Interaction) -> bool:
        """부른 사람이 있는 음성 채널로 들어간다."""
        voice_state = getattr(interaction.user, "voice", None)
        if voice_state is None or voice_state.channel is None:
            await interaction.followup.send(self.bot.persona.line("music_no_voice"))
            return False

        voice = interaction.guild.voice_client
        if voice is None:
            await voice_state.channel.connect()
        elif voice.channel != voice_state.channel:
            await voice.move_to(voice_state.channel)
        return True

    @app_commands.command(name="play", description="음악을 재생합니다. 검색어나 유튜브·스포티파이 링크.")
    @app_commands.describe(query="검색어, 유튜브 링크, 또는 스포티파이 트랙·앨범·플레이리스트 링크")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        if not await self.join(interaction):
            return

        player = self.player_for(interaction)
        who = interaction.user.display_name

        link = parse_link(query)
        if link and self.spotify is None:
            await interaction.followup.send(self.bot.persona.line("music_no_spotify"))
            return

        if link:
            try:
                name, names = await self.spotify.resolve(*link, limit=PLAYLIST_LIMIT)
            except SpotifyError as error:
                await interaction.followup.send(
                    f"{self.bot.persona.line('error')}\n`{error}`"
                )
                return
            if not names:
                await interaction.followup.send(self.bot.persona.line("music_empty_list"))
                return
            for title in names:
                player.add(Track(query=title, title=title, requester=who))
            await interaction.followup.send(
                self.bot.persona.line("music_playlist", name=name, count=len(names))
            )
            return

        player.add(Track(query=query, title=query, requester=who))
        await interaction.followup.send(
            self.bot.persona.line("music_queued", title=query)
        )

    @app_commands.command(name="skip", description="지금 곡을 건너뜁니다.")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction):
        voice = interaction.guild.voice_client
        if voice is None or not voice.is_playing():
            await interaction.response.send_message(self.bot.persona.line("music_nothing"))
            return
        voice.stop()
        await interaction.response.send_message(self.bot.persona.line("music_skipped"))

    @app_commands.command(name="queue", description="대기열을 봅니다.")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if player is None or (player.current is None and not player.pending):
            await interaction.response.send_message(self.bot.persona.line("music_nothing"))
            return

        lines = []
        if player.current:
            lines.append(f"지금: {player.current.title}")
        upcoming = list(player.pending)[:QUEUE_PREVIEW]
        lines += [f"{i}. {t.title}" for i, t in enumerate(upcoming, 1)]
        rest = len(player.pending) - len(upcoming)
        if rest > 0:
            lines.append(f"그리고 {rest}개 더.")
        await interaction.response.send_message(
            f"{self.bot.persona.line('music_queue')}\n" + "\n".join(lines)
        )

    @app_commands.command(name="stop", description="재생을 멈추고 음성 채널에서 나갑니다.")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        player = self.players.pop(interaction.guild.id, None)
        if player:
            player.stop()
        voice = interaction.guild.voice_client
        if voice:
            await voice.disconnect()
        await interaction.response.send_message(self.bot.persona.line("music_stopped"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
    if not (os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET")):
        logger.warning("스포티파이 자격증명이 없어 링크 대신 검색어만 받습니다.")
