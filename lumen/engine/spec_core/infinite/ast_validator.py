"""Strict validator — DynamicBotSpec (architecture plan)."""
from __future__ import annotations

from typing import Any

from ..dynamic_bot_spec import DynamicBotSpec, parse_dynamic_spec


class SpecValidationError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


def validate_dynamic_spec(spec: DynamicBotSpec | dict[str, Any]) -> DynamicBotSpec:
    try:
        return parse_dynamic_spec(spec)
    except Exception as exc:
        msg = str(exc)
        low = msg.lower()
        if "loop" in low:
            raise SpecValidationError("infinite_loop_detected", msg[:200]) from exc
        if "depth" in low:
            raise SpecValidationError("dag_depth_exceeded", msg[:200]) from exc
        if "unsafe" in low or "non-deterministic" in low:
            raise SpecValidationError("unsafe_atom", msg[:200]) from exc
        raise SpecValidationError("schema_invalid", msg[:400]) from exc


def validation_errors_for_llm(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, SpecValidationError):
        return {"ok": False, "code": exc.code, "detail": exc.detail}
    return {"ok": False, "code": "schema_invalid", "detail": str(exc)[:400]}
