"""스포티파이 링크를 곡 이름 목록으로 바꾼다.

스포티파이는 오디오를 주지 않는다. 여기서 얻는 것은 '무엇을 틀지'뿐이고,
소리는 다른 곳에서 가져온다.

사용자 로그인이 필요 없는 클라이언트 자격증명 방식을 쓴다. 공개 플레이리스트·
앨범·트랙을 읽는 데는 이것으로 충분하다. 남의 재생 상태를 보거나 조작하려면
사용자별 OAuth가 필요하지만, 그건 여기서 하는 일이 아니다.
"""

from __future__ import annotations

import re
import time

import aiohttp

TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"

#: open.spotify.com/<종류>/<id> 와 spotify:<종류>:<id> 를 모두 받는다.
LINK = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z]+/)?|spotify:)(track|album|playlist)[/:]([A-Za-z0-9]+)"
)
#: 한 번에 받아오는 곡 수. 스포티파이 상한이 100이다.
PAGE = 100


class SpotifyError(RuntimeError):
    pass


def parse_link(text: str) -> tuple[str, str] | None:
    """스포티파이 링크면 (종류, id), 아니면 None."""
    match = LINK.search(text)
    return (match.group(1), match.group(2)) if match else None


def track_name(track: dict) -> str:
    """검색어로 쓸 '아티스트 - 제목'. 유튜브에서 찾을 때 쓴다."""
    artists = ", ".join(a["name"] for a in track.get("artists", []))
    title = track.get("name", "")
    return f"{artists} - {title}" if artists else title


class Spotify:
    """토큰을 알아서 갱신하는 최소한의 클라이언트."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = ""
        self._expires = 0.0

    async def _auth(self, session: aiohttp.ClientSession) -> str:
        if self._token and time.monotonic() < self._expires:
            return self._token

        async with session.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=aiohttp.BasicAuth(self.client_id, self.client_secret),
        ) as resp:
            if resp.status != 200:
                raise SpotifyError(f"토큰 발급 실패 ({resp.status}). 아이디와 시크릿을 확인하세요.")
            body = await resp.json()

        self._token = body["access_token"]
        # 만료 직전에 갱신되도록 30초 여유를 둔다.
        self._expires = time.monotonic() + body.get("expires_in", 3600) - 30
        return self._token

    async def _get(self, session: aiohttp.ClientSession, path: str, **params) -> dict:
        token = await self._auth(session)
        async with session.get(
            f"{API}/{path}",
            headers={"Authorization": f"Bearer {token}"},
            params={k: v for k, v in params.items() if v is not None},
        ) as resp:
            if resp.status == 404:
                raise SpotifyError("스포티파이에서 찾을 수 없습니다. 비공개 항목일 수 있습니다.")
            if resp.status != 200:
                raise SpotifyError(f"스포티파이 요청 실패 ({resp.status}).")
            return await resp.json()

    async def resolve(self, kind: str, spotify_id: str, limit: int) -> tuple[str, list[str]]:
        """링크 하나를 (이름, 곡 목록)으로 푼다. 곡은 '아티스트 - 제목' 형식."""
        async with aiohttp.ClientSession() as session:
            if kind == "track":
                track = await self._get(session, f"tracks/{spotify_id}")
                return track_name(track), [track_name(track)]

            if kind == "album":
                album = await self._get(session, f"albums/{spotify_id}")
                items = await self._pages(
                    session, f"albums/{spotify_id}/tracks", limit, lambda t: t
                )
                return album.get("name", "앨범"), [track_name(t) for t in items]

            playlist = await self._get(session, f"playlists/{spotify_id}", fields="name")
            items = await self._pages(
                session,
                f"playlists/{spotify_id}/tracks",
                limit,
                lambda item: item.get("track"),
            )
            return playlist.get("name", "플레이리스트"), [track_name(t) for t in items]

    async def _pages(self, session, path: str, limit: int, pick) -> list[dict]:
        """페이지를 넘겨가며 limit개까지 모은다. 재생 불가능한 항목은 버린다."""
        out: list[dict] = []
        offset = 0
        while len(out) < limit:
            body = await self._get(
                session, path, limit=min(PAGE, limit - len(out)), offset=offset
            )
            items = body.get("items", [])
            if not items:
                break
            for item in items:
                track = pick(item)
                # 지역 제한이나 삭제로 빈 항목이 섞여 온다. 로컬 파일도 재생할 수 없다.
                if track and track.get("name") and not track.get("is_local"):
                    out.append(track)
            if not body.get("next"):
                break
            offset += len(items)
        return out[:limit]
