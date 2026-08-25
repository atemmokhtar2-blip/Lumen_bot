"""Infinite engine package — delegates to architecture-plan DynamicBotSpec."""
from __future__ import annotations

from ..dynamic_bot_spec import (
    ALLOWED_ACTIONS,
    ALLOWED_CONDITIONS,
    ALLOWED_TRANSFORMERS,
    ALLOWED_TRIGGERS,
    Action,
    Condition,
    DynamicBotSpec,
    FlowNode,
    Transformer,
    Trigger,
    parse_dynamic_spec,
)
from ..rule_engine import run_rule_engine
from .ast_validator import SpecValidationError, validate_dynamic_spec
from .compose import compose_infinite_from_payload, try_compose_infinite, execute_infinite
from .engine_router import route_and_execute
from .llm_contract import SYSTEM_PROMPT_INFINITE, dynamic_spec_json_schema
from .macro_registry import MacroRegistry, get_macro_registry
from .macro_discovery import list_macro_hints, macros_for_prompt, suggest_macros_for_user
from .api_proxy import proxy_request, validate_egress_url

# back-compat names
TriggerAtom = Trigger
ConditionAtom = Condition
ActionAtom = Action
TransformerAtom = Transformer
compile_dynamic_spec = lambda s: compose_infinite_from_payload(
    s if isinstance(s, dict) else s.model_dump()
)[0]
render_handlers_python = lambda s: "# use run_rule_engine — plan renderer"

__all__ = [
    "ALLOWED_TRIGGERS",
    "ALLOWED_CONDITIONS",
    "ALLOWED_ACTIONS",
    "ALLOWED_TRANSFORMERS",
    "Trigger",
    "Condition",
    "Action",
    "Transformer",
    "FlowNode",
    "DynamicBotSpec",
    "parse_dynamic_spec",
    "validate_dynamic_spec",
    "SpecValidationError",
    "run_rule_engine",
    "route_and_execute",
    "compose_infinite_from_payload",
    "try_compose_infinite",
    "execute_infinite",
    "SYSTEM_PROMPT_INFINITE",
    "dynamic_spec_json_schema",
    "MacroRegistry",
    "get_macro_registry",
    "list_macro_hints",
    "macros_for_prompt",
    "suggest_macros_for_user",
    "proxy_request",
    "validate_egress_url",
]
