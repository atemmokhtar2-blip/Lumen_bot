"""Compose path: LLM JSON → DynamicBotSpec (plan model) → BotSpec + rule engine."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from ..dynamic_bot_spec import DynamicBotSpec, parse_dynamic_spec
from ..rule_engine import run_rule_engine
from ..schema import (
    Action,
    BotMeta,
    BotSpec,
    Feature,
    Messages,
    Trigger as LegacyTrigger,
)

logger = logging.getLogger(__name__)
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S | re.I)


class SpecValidationError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


def parse_llm_spec_payload(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = (raw or "").strip()
    if not text:
        raise SpecValidationError("empty_payload")
    m = _JSON_BLOCK.search(text)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise SpecValidationError("json_parse_failed")


def validate_dynamic_spec(data: dict[str, Any] | DynamicBotSpec) -> DynamicBotSpec:
    try:
        return parse_dynamic_spec(data)
    except Exception as exc:
        raise SpecValidationError("schema_invalid", str(exc)[:400]) from exc


def _dyn_to_botspec(dyn: DynamicBotSpec) -> BotSpec:
    features: list[Feature] = []
    for node in dyn.nodes:
        t = node.trigger
        if t.type == "on_command":
            leg = LegacyTrigger(
                "command",
                str((t.config or {}).get("command") or node.id).lstrip("/"),
            )
        elif t.type == "on_message":
            leg = LegacyTrigger("message", node.id)
        else:
            leg = LegacyTrigger("command", node.id)
        text = ""
        for a in node.actions:
            if a.type == "send_message":
                text = str((a.config or {}).get("text") or text)
        features.append(
            Feature(
                id=node.id,
                feature="help" if leg.id != "start" else "start",
                trigger=leg,
                action=Action("rule_engine", node.id),
                messages=Messages(success=text or f"OK:{node.id}"),
            )
        )
    if not any(
        f.trigger.type == "command" and f.trigger.id == "start" for f in features
    ):
        features.insert(
            0,
            Feature(
                id="auto_start",
                feature="start",
                trigger=LegacyTrigger("command", "start"),
                action=Action("core", "start"),
                messages=Messages(success=f"مرحباً بك في {dyn.bot_name}"),
            ),
        )
    return BotSpec(
        bot=BotMeta(
            name=dyn.bot_name,
            language=dyn.language,
            description=dyn.description,
        ),
        features=features,
        hard_constraints=["engine:infinite_v1", "atoms:plan_v1"],
        seed_data={"_infinite_spec": [dyn.model_dump()]},
    )


def compose_infinite_from_payload(
    payload: str | dict[str, Any],
    *,
    promote_on_success: bool = False,
) -> tuple[BotSpec, DynamicBotSpec]:
    data = parse_llm_spec_payload(payload)
    dyn = validate_dynamic_spec(data)
    bot = _dyn_to_botspec(dyn)
    if promote_on_success:
        try:
            from .macro_registry import get_macro_registry

            get_macro_registry().promote(dyn.model_dump(), score=1.0)
        except Exception:
            logger.exception("macro promote failed")
    return bot, dyn


def try_compose_infinite(
    payload: str | dict[str, Any],
) -> tuple[Optional[BotSpec], Optional[DynamicBotSpec], Optional[dict[str, Any]]]:
    try:
        bot, dyn = compose_infinite_from_payload(payload)
        return bot, dyn, None
    except SpecValidationError as exc:
        return None, None, {"ok": False, "code": exc.code, "detail": exc.detail}
    except Exception as exc:
        return None, None, {
            "ok": False,
            "code": "schema_invalid",
            "detail": str(exc)[:400],
        }


def execute_infinite(
    payload: str | dict[str, Any],
    event: dict[str, Any],
    *,
    state: dict | None = None,
) -> dict[str, Any]:
    data = (
        parse_llm_spec_payload(payload)
        if not isinstance(payload, DynamicBotSpec)
        else payload.model_dump()
    )
    dyn = validate_dynamic_spec(data)
    return run_rule_engine(dyn, event, state=state)
