"""음성 채널에서 음악을 재생한다.

소리는 유튜브에서 가져온다. 스포티파이는 오디오를 주지 않으므로 '무엇을 틀지'만
담당한다 — 스포티파이 링크를 받으면 곡 이름 목록으로 풀고, 각 곡을 유튜브에서
찾아 재생한다.

재생목록은 서버마다 따로 돌아간다. 각 서버의 Player가 목록 하나와 지금 위치를
들고, 백그라운드 작업이 위치를 옮겨 가며 재생한다. 곡을 꺼내 버리지 않으므로
끝까지 가면 처음으로 돌아갈 수 있다. 새 곡 없이 IDLE_TIMEOUT이 지나면 나간다.
"""

import asyncio
import logging
import os
import shutil
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
#: /playlist로 한 번에 보여줄 곡 수.
LIST_PREVIEW = 15
#: 음량. 1.0이 원본 크기인데 유튜브 음원은 그대로면 대체로 시끄럽다.
DEFAULT_VOLUME = 0.3
VOLUME_STEP = 0.1
MAX_VOLUME = 2.0

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


def ffmpeg_path() -> str:
    """쓸 FFmpeg 실행 파일.

    PATH에 있으면 그것을 쓰고, 없으면 imageio-ffmpeg가 requirements로 함께
    가져온 것을 쓴다. 덕분에 FFmpeg를 따로 설치하거나 PATH를 건드릴 필요가 없다.
    """
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        logger.warning("FFmpeg를 찾지 못했습니다. 재생이 실패합니다.")
        return "ffmpeg"


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


class Controls(discord.ui.View):
    """재생 중에 채팅창에 띄우는 조작 버튼.

    누른 사람을 가리지 않는다. 같은 음성 채널에서 같이 듣는 사람이라면
    누구든 넘기고 멈출 수 있어야 편하다.
    """

    def __init__(self, player: "Player"):
        super().__init__(timeout=None)
        self.player = player
        self.refresh()

    def refresh(self):
        """일시정지 버튼의 표시를 지금 상태에 맞춘다."""
        voice = self.player.guild.voice_client
        paused = bool(voice and voice.is_paused())
        self.toggle.emoji = "▶️" if paused else "⏸️"
        self.loop_all.style = (
            discord.ButtonStyle.success
            if self.player.loop_all
            else discord.ButtonStyle.secondary
        )

    async def apply(self, interaction: discord.Interaction):
        """버튼을 누른 자리에서 패널을 갱신한다."""
        self.refresh()
        await interaction.response.edit_message(embed=self.player.panel_embed(), view=self)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice = self.player.guild.voice_client
        if voice is None:
            await self.apply(interaction)
            return
        if voice.is_paused():
            voice.resume()
        elif voice.is_playing():
            voice.pause()
        await self.apply(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice = self.player.guild.voice_client
        if voice and (voice.is_playing() or voice.is_paused()):
            # stop()이 after 콜백을 부르고, 재생 루프가 다음 곡으로 넘어간다.
            voice.stop()
        await self.apply(interaction)

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary)
    async def quieter(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.set_volume(self.player.volume - VOLUME_STEP)
        await self.apply(interaction)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary)
    async def louder(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.set_volume(self.player.volume + VOLUME_STEP)
        await self.apply(interaction)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def loop_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.loop_all = not self.player.loop_all
        await self.apply(interaction)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger)
    async def stop_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.player
        player.stop()
        voice = player.guild.voice_client
        if voice:
            await voice.disconnect()
        player.cog.players.pop(player.guild.id, None)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=player.say("music_stopped"), embed=None, view=self
        )
        self.stop()


class Player:
    """서버 한 곳의 대기열과 재생 루프."""

    def __init__(self, cog: "Music", guild: discord.Guild, channel: discord.abc.Messageable):
        self.cog = cog
        self.guild = guild
        self.channel = channel
        # 꺼내 버리는 대기열이 아니라 유지되는 재생목록이다. 곡을 소모하지 않고
        # 위치만 옮기기 때문에 끝까지 가면 처음으로 돌아갈 수 있다.
        self.tracks: list[Track] = []
        self.index = 0
        self.loop_all = True
        self.added = asyncio.Event()
        self.advance = asyncio.Event()
        self.current: Track | None = None
        self.volume = DEFAULT_VOLUME
        #: 조작 패널. 곡이 바뀔 때마다 새로 보내지 않고 이 메시지를 고쳐 쓴다.
        self.panel: discord.Message | None = None
        # bot.loop은 봇이 켜진 뒤에만 접근된다. 지금 도는 루프를 직접 잡아 둔다.
        # 재생 종료 콜백이 다른 스레드에서 오므로 그때도 이 참조가 필요하다.
        self.loop = asyncio.get_running_loop()
        self.task = self.loop.create_task(self.run())

    def say(self, key: str, **kwargs) -> str:
        return self.cog.bot.persona.line(key, **kwargs)

    async def next_track(self) -> Track | None:
        """다음에 틀 곡. 없으면 새 곡이 들어오기를 기다리고, 시간이 다 되면 None."""
        while True:
            if self.index >= len(self.tracks):
                if self.tracks and self.loop_all:
                    self.index = 0
                    continue
                self.added.clear()
                try:
                    await asyncio.wait_for(self.added.wait(), timeout=IDLE_TIMEOUT)
                except asyncio.TimeoutError:
                    return None
                continue
            return self.tracks[self.index]

    async def run(self):
        while True:
            self.advance.clear()
            track = await self.next_track()
            if track is None:
                await self.disconnect()
                return

            try:
                info = await asyncio.to_thread(extract, track.query)
            except Exception:
                logger.exception("'%s' 를 찾지 못했다", track.query)
                await self.send(self.say("music_not_found", query=track.title))
                self.index += 1
                continue

            # 음량을 조절하려면 PCM으로 받아야 한다. Opus로 받으면 이미 압축된
            # 뒤라 중간에 크기를 바꿀 수 없다.
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(
                    info["url"], executable=self.cog.ffmpeg, **FFMPEG_OPTS
                ),
                volume=self.volume,
            )
            self.current = track._replace(title=info.get("title") or track.title)

            voice = self.guild.voice_client
            if voice is None or not voice.is_connected():
                return
            voice.play(source, after=self._finished)
            await self.show_panel()

            await self.advance.wait()
            self.current = None
            self.index += 1

    def _finished(self, error: Exception | None):
        if error:
            logger.error("재생 중 오류: %s", error)
        self.loop.call_soon_threadsafe(self.advance.set)

    async def send(self, text: str):
        try:
            await self.channel.send(text)
        except discord.HTTPException:
            logger.exception("메시지 전송 실패")

    async def disconnect(self):
        voice = self.guild.voice_client
        if voice:
            await voice.disconnect()
        await self.retire_panel()
        self.cog.players.pop(self.guild.id, None)

    async def retire_panel(self):
        """더 이상 조작할 것이 없으면 패널의 버튼을 죽인다."""
        if self.panel is None:
            return
        try:
            await self.panel.edit(embed=None, view=None)
        except discord.HTTPException:
            pass
        self.panel = None

    def set_volume(self, value: float):
        self.volume = max(0.0, min(MAX_VOLUME, round(value, 2)))
        voice = self.guild.voice_client
        if voice and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = self.volume

    def panel_embed(self) -> discord.Embed:
        embed = discord.Embed(color=self.cog.bot.persona.color)
        embed.add_field(
            name="지금", value=self.current.title if self.current else "없음", inline=False
        )
        position = f"{self.index + 1} / {len(self.tracks)}" if self.tracks else "0 / 0"
        embed.add_field(name="목록", value=position, inline=True)
        embed.add_field(name="음량", value=f"{round(self.volume * 100)}%", inline=True)
        embed.add_field(name="반복", value="켜짐" if self.loop_all else "꺼짐", inline=True)
        return embed

    async def show_panel(self):
        """조작 패널을 띄운다. 이미 있으면 새로 보내지 않고 고쳐 쓴다."""
        line = self.say("music_now", title=self.current.title)
        view = Controls(self)
        if self.panel is not None:
            try:
                await self.panel.edit(content=line, embed=self.panel_embed(), view=view)
                return
            except discord.HTTPException:
                # 누가 지웠다. 아래에서 새로 보낸다.
                self.panel = None
        try:
            self.panel = await self.channel.send(
                line, embed=self.panel_embed(), view=view
            )
        except discord.HTTPException:
            logger.exception("패널 전송 실패")

    def add(self, track: Track):
        self.tracks.append(track)
        self.added.set()

    def remove(self, position: int) -> Track | None:
        """1부터 세는 번호로 한 곡을 뺀다. 없는 번호면 None.

        앞쪽을 빼면 현재 위치가 한 칸 당겨진다. 지금 틀고 있는 곡을 뺐다면
        재생을 멈춰서 다음 곡으로 넘어가게 한다 — run()이 뒤에 index를 1
        올리므로 여기서 미리 1을 내려 두어야 다음 곡을 건너뛰지 않는다.
        """
        i = position - 1
        if not 0 <= i < len(self.tracks):
            return None

        removed = self.tracks.pop(i)
        playing_now = i == self.index
        if i <= self.index:
            self.index -= 1
        if playing_now:
            voice = self.guild.voice_client
            if voice and (voice.is_playing() or voice.is_paused()):
                voice.stop()
        return removed

    def stop(self):
        self.task.cancel()
        self.tracks.clear()
        self.index = 0


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, Player] = {}
        self.ffmpeg = ffmpeg_path()
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

    def voice_channel_of(self, interaction: discord.Interaction):
        """부른 사람이 있는 음성 채널. 없으면 None.

        Member.voice는 캐시를 읽는 값이라 큰 서버에서 비어 있을 수 있다.
        그때는 채널을 직접 훑어서 찾는다.
        """
        state = getattr(interaction.user, "voice", None)
        if state and state.channel:
            return state.channel
        for channel in interaction.guild.voice_channels:
            if any(m.id == interaction.user.id for m in channel.members):
                return channel
        return None

    async def join(self, interaction: discord.Interaction) -> bool:
        """부른 사람이 있는 음성 채널로 들어간다."""
        channel = self.voice_channel_of(interaction)
        if channel is None:
            await interaction.followup.send(self.bot.persona.line("music_no_voice"))
            return False

        # 권한이 없어 못 들어가는 것과 아예 안 들어와 있는 것은 다른 문제다.
        # 둘을 같은 말로 알리면 원인을 찾을 수 없다.
        perms = channel.permissions_for(interaction.guild.me)
        missing = [
            name
            for name, ok in (("채널 보기", perms.view_channel), ("연결", perms.connect), ("말하기", perms.speak))
            if not ok
        ]
        if missing:
            await interaction.followup.send(
                self.bot.persona.line(
                    "music_cant_join", channel=channel.name, missing=", ".join(missing)
                )
            )
            return False

        voice = interaction.guild.voice_client
        try:
            if voice is None:
                await channel.connect()
            elif voice.channel != channel:
                await voice.move_to(channel)
        except (discord.ClientException, asyncio.TimeoutError, discord.HTTPException) as error:
            logger.exception("'%s' 에 들어가지 못했다", channel.name)
            await interaction.followup.send(
                f"{self.bot.persona.line('error')}\n`{type(error).__name__}: {error}`"
            )
            return False
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

    @app_commands.command(name="playlist", description="재생목록을 보거나 곡을 뺍니다.")
    @app_commands.describe(remove="뺄 곡의 번호. 비우면 목록만 봅니다.")
    @app_commands.guild_only()
    async def playlist(
        self, interaction: discord.Interaction, remove: int | None = None
    ):
        player = self.players.get(interaction.guild.id)
        if player is None or not player.tracks:
            await interaction.response.send_message(self.bot.persona.line("music_nothing"))
            return

        line = self.bot.persona.line("music_queue")
        if remove is not None:
            dropped = player.remove(remove)
            if dropped is None:
                await interaction.response.send_message(
                    self.bot.persona.line("music_no_such_track", position=remove)
                )
                return
            line = self.bot.persona.line("music_removed", title=dropped.title)
            if not player.tracks:
                await interaction.response.send_message(line)
                return

        await interaction.response.send_message(line, embed=self.listing(player))

    def listing(self, player: Player) -> discord.Embed:
        """번호 붙은 재생목록. 지금 곡에 표시를 남긴다."""
        embed = discord.Embed(color=self.bot.persona.color)
        rows = []
        for i, track in enumerate(player.tracks[:LIST_PREVIEW], 1):
            mark = "▶ " if i - 1 == player.index else "　 "
            rows.append(f"{mark}{i}. {track.title}"[:100])
        rest = len(player.tracks) - LIST_PREVIEW
        if rest > 0:
            rows.append(f"　 ...그리고 {rest}곡 더.")
        embed.description = "\n".join(rows)
        embed.set_footer(
            text=f"{len(player.tracks)}곡 · 반복 {'켜짐' if player.loop_all else '꺼짐'}"
        )
        return embed

    @app_commands.command(name="stop", description="재생을 멈추고 음성 채널에서 나갑니다.")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        player = self.players.pop(interaction.guild.id, None)
        if player:
            player.stop()
            await player.retire_panel()
        voice = interaction.guild.voice_client
        if voice:
            await voice.disconnect()
        await interaction.response.send_message(self.bot.persona.line("music_stopped"))


async def setup(bot: commands.Bot):
    cog = Music(bot)
    await bot.add_cog(cog)
    logger.info("FFmpeg: %s", cog.ffmpeg)
    if not (os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET")):
        logger.warning("스포티파이 자격증명이 없어 링크 대신 검색어만 받습니다.")
