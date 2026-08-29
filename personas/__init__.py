import importlib

from .base import Persona

__all__ = ["Persona", "load_persona"]


def load_persona(key: str) -> Persona:
    """personas/<key>.py 에서 PERSONA를 읽어온다."""
    try:
        module = importlib.import_module(f"personas.{key}")
    except ModuleNotFoundError as exc:
        raise ValueError(
            f"'{key}' 페르소나를 찾을 수 없습니다. personas/{key}.py 가 있는지 확인하세요."
        ) from exc

    persona = getattr(module, "PERSONA", None)
    if not isinstance(persona, Persona):
        raise ValueError(f"personas/{key}.py 는 Persona 인스턴스인 PERSONA를 정의해야 합니다.")
    return persona
