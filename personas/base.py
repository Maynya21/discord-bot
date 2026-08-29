"""페르소나 공통 자료구조.

각 페르소나 모듈은 `PERSONA`라는 이름으로 Persona 인스턴스 하나를 노출한다.
명령어 코드는 이 인터페이스만 알면 되고, 어떤 캐릭터인지는 알 필요가 없다.

대사에서 '* '로 시작하는 줄은 서술자 목소리다. 원문에는 그대로 두고,
디스코드로 보낼 때 `narrator_style`에 따라 꾸며진다. 이 변환이 없으면
'* '가 디스코드 마크다운의 글머리 기호로 해석되어 목록처럼 보인다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import NamedTuple

#: 서술자 목소리 줄임표. personas/*.md 의 표기와 같다.
NARRATOR_PREFIX = "* "

#: 서술자 줄을 디스코드에서 어떻게 보여줄지.
#: - "italic": *기울임*. 모든 기기에서 동작하고 본문 흐름을 유지한다.
#: - "ansi":   ANSI 코드블록으로 색을 입힌다. PC에서만 색이 나오고,
#:             코드블록이라 고정폭 글꼴에 테두리가 생긴다.
#: - "plain":  꾸미지 않고 '* '만 떼어낸다.
NARRATOR_STYLES = ("italic", "ansi", "plain")

#: ANSI 스타일에서 쓰는 전경색 코드. 디스코드가 해석하는 값만 추렸다.
ANSI_COLORS = {
    "gray": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "pink": 35,
    "cyan": 36,
    "white": 37,
}


class Speech(NamedTuple):
    """한 번의 발화. 디스코드로 보낼 본문과 그때 쓸 임베드 색."""

    text: str
    color: int


@dataclass
class Persona:
    #: personas/<key>.py 의 파일명과 같아야 한다. .env의 PERSONA= 값으로 쓰인다.
    key: str
    #: 임베드 등에 표시할 이름.
    name: str
    #: 평상시 임베드 색상.
    color: int
    #: 무거운 대사에만 쓰는 색. None이면 색을 나누지 않고 항상 color를 쓴다.
    accent_color: int | None = None
    #: 내용과 무관하게 항상 accent_color로 나갈 대사 키.
    accent_keys: frozenset[str] = frozenset()
    #: 고정 대사. 값은 후보 목록이고, 호출할 때마다 하나를 골라 쓴다.
    lines: dict[str, list[str]] = field(default_factory=dict)
    #: AI 대화 기능이 시스템 프롬프트로 쓸 마크다운 문서. personas/ 기준 상대 경로.
    prompt_file: str = ""
    #: 서술자 줄의 표시 방식. NARRATOR_STYLES 중 하나.
    narrator_style: str = "italic"
    #: narrator_style이 "ansi"일 때 쓸 색. ANSI_COLORS의 키.
    narrator_color: str = "red"
    #: True면 서술자 표기가 없어도 마지막 줄을 항상 강조한다.
    accent_last_line: bool = False

    def __post_init__(self) -> None:
        if self.narrator_style not in NARRATOR_STYLES:
            raise ValueError(
                f"narrator_style은 {NARRATOR_STYLES} 중 하나여야 합니다: {self.narrator_style!r}"
            )
        if self.narrator_color not in ANSI_COLORS:
            raise ValueError(
                f"narrator_color는 {tuple(ANSI_COLORS)} 중 하나여야 합니다: {self.narrator_color!r}"
            )

    def speak(self, key: str, **kwargs: object) -> Speech:
        """대사 하나를 골라 본문과 임베드 색을 함께 반환한다."""
        raw = self.raw_line(key, **kwargs)
        return Speech(self.decorate(raw), self.color_for(key, raw))

    def line(self, key: str, **kwargs: object) -> str:
        """`key`에 해당하는 대사 하나를 골라 디스코드용으로 꾸며서 반환한다."""
        return self.decorate(self.raw_line(key, **kwargs))

    def color_for(self, key: str, raw: str) -> int:
        """이 발화에 쓸 임베드 색.

        서술자 목소리가 섞인 대사만 accent_color로 나간다. 서술자 줄은 원래
        아껴 쓰는 장치라, 색을 따로 관리하지 않아도 강조 빈도가 따라간다.
        `raw`는 꾸미기 전 원문이어야 한다. 꾸미고 나면 '* ' 표기가 사라진다.
        """
        if self.accent_color is None:
            return self.color
        if self.accent_last_line or key in self.accent_keys or self.has_narrator(raw):
            return self.accent_color
        return self.color

    @staticmethod
    def has_narrator(raw: str) -> bool:
        """원문에 서술자 목소리 줄이 있는지."""
        return any(line.startswith(NARRATOR_PREFIX) for line in raw.split("\n"))

    def raw_line(self, key: str, **kwargs: object) -> str:
        """대사 원문. 서술자 표기('* ')가 그대로 남아 있다."""
        variants = self.lines.get(key)
        if not variants:
            raise KeyError(f"페르소나 '{self.key}'에 '{key}' 대사가 정의되어 있지 않다.")
        return random.choice(variants).format(**kwargs)

    def decorate(self, text: str) -> str:
        """강조할 줄에 디스코드 마크다운을 입힌다.

        서술자 표기('* ')가 붙은 줄이 대상이고, accent_last_line이 켜져 있으면
        표기와 무관하게 마지막 줄도 함께 강조한다.
        """
        lines = text.split("\n")
        last = len(lines) - 1
        out = []
        for i, line in enumerate(lines):
            if line.startswith(NARRATOR_PREFIX):
                out.append(self._decorate_narrator(line[len(NARRATOR_PREFIX) :].strip()))
            elif self.accent_last_line and i == last:
                out.append(self._decorate_narrator(line.strip()))
            else:
                out.append(line)
        return "\n".join(out)

    def _decorate_narrator(self, body: str) -> str:
        if not body:
            return ""
        if self.narrator_style == "ansi":
            code = ANSI_COLORS[self.narrator_color]
            return f"```ansi\n\x1b[0;{code}m{body}\x1b[0m\n```"
        if self.narrator_style == "italic":
            return f"*{body}*"
        return body

    @cached_property
    def system_prompt(self) -> str:
        """페르소나 문서 전문. AI 대화 기능이 붙을 때 시스템 프롬프트로 넘긴다."""
        if not self.prompt_file:
            return ""
        return (Path(__file__).parent / self.prompt_file).read_text(encoding="utf-8")
