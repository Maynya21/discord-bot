"""페르소나 공통 자료구조.

각 페르소나 모듈은 `PERSONA`라는 이름으로 Persona 인스턴스 하나를 노출한다.
명령어 코드는 이 인터페이스만 알면 되고, 어떤 캐릭터인지는 알 필요가 없다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path


@dataclass
class Persona:
    #: personas/<key>.py 의 파일명과 같아야 한다. .env의 PERSONA= 값으로 쓰인다.
    key: str
    #: 임베드 등에 표시할 이름.
    name: str
    #: 임베드 색상.
    color: int
    #: 고정 대사. 값은 후보 목록이고, 호출할 때마다 하나를 골라 쓴다.
    lines: dict[str, list[str]] = field(default_factory=dict)
    #: AI 대화 기능이 시스템 프롬프트로 쓸 마크다운 문서. personas/ 기준 상대 경로.
    prompt_file: str = ""

    def line(self, key: str, **kwargs: object) -> str:
        """`key`에 해당하는 대사 후보 중 하나를 골라 반환한다."""
        variants = self.lines.get(key)
        if not variants:
            raise KeyError(f"페르소나 '{self.key}'에 '{key}' 대사가 정의되어 있지 않다.")
        return random.choice(variants).format(**kwargs)

    @cached_property
    def system_prompt(self) -> str:
        """페르소나 문서 전문. AI 대화 기능이 붙을 때 시스템 프롬프트로 넘긴다."""
        if not self.prompt_file:
            return ""
        return (Path(__file__).parent / self.prompt_file).read_text(encoding="utf-8")
