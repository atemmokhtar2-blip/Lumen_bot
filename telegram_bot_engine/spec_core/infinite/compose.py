"""High-level entry: text/JSON → validated DynamicBotSpec → BotSpec."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from ..schema import BotSpec
from .ast_validator import SpecValidationError, validate_dynamic_spec, validation_errors_for_llm
from .infinite_schema import DynamicBotSpec
from .jit_compiler import compile_dynamic_spec, render_handlers_python
from .macro_registry import get_macro_registry

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S | re.I)


def parse_llm_spec_payload(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = (raw or "").strip()
    if not text:
        raise SpecValidationError("empty_payload")
    m = _JSON_BLOCK.search(text)
    if m:
        text = m.group(1)
    # try whole text as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # find first { ... }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise SpecValidationError("json_parse_failed")


def compose_infinite_from_payload(
    payload: str | dict[str, Any],
    *,
    promote_on_success: bool = False,
) -> tuple[BotSpec, DynamicBotSpec]:
    """Validate infinite JSON and compile to BotSpec."""
    data = parse_llm_spec_payload(payload)
    dyn = validate_dynamic_spec(data)
    bot_spec = compile_dynamic_spec(dyn)
    if promote_on_success:
        try:
            get_macro_registry().promote(dyn, score=1.0)
        except Exception:
            logger.exception("macro promote failed")
    return bot_spec, dyn


def try_compose_infinite(
    payload: str | dict[str, Any],
) -> tuple[Optional[BotSpec], Optional[DynamicBotSpec], Optional[dict[str, Any]]]:
    """Non-raising API for repair loops: returns (spec, dyn, error_dict)."""
    try:
        bot, dyn = compose_infinite_from_payload(payload)
        return bot, dyn, None
    except Exception as exc:
        return None, None, validation_errors_for_llm(exc)
