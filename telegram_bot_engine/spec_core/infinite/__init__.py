"""Infinite Spec Engine — atomic primitives + JIT compiler + macro registry.

LLM emits DynamicBotSpec JSON (atoms only). Validator enforces DAG safety.
Renderer compiles to BotSpec / executable handlers. Successful specs can
promote to macros (self-expanding registry).
"""
from __future__ import annotations

from .atomic_primitives import (
    ALLOWED_ACTIONS,
    ALLOWED_CONDITIONS,
    ALLOWED_TRANSFORMERS,
    ALLOWED_TRIGGERS,
)
from .infinite_schema import (
    ActionAtom,
    ConditionAtom,
    DynamicBotSpec,
    FlowNode,
    TriggerAtom,
    TransformerAtom,
)
from .ast_validator import SpecValidationError, validate_dynamic_spec
from .jit_compiler import compile_dynamic_spec, render_handlers_python
from .macro_registry import MacroRegistry, get_macro_registry
from .llm_contract import dynamic_spec_json_schema, SYSTEM_PROMPT_INFINITE
from .engine_router import route_and_execute
from .api_proxy import proxy_request, validate_egress_url

__all__ = [
    "ALLOWED_TRIGGERS",
    "ALLOWED_CONDITIONS",
    "ALLOWED_ACTIONS",
    "ALLOWED_TRANSFORMERS",
    "TriggerAtom",
    "ConditionAtom",
    "ActionAtom",
    "TransformerAtom",
    "FlowNode",
    "DynamicBotSpec",
    "SpecValidationError",
    "validate_dynamic_spec",
    "compile_dynamic_spec",
    "render_handlers_python",
    "MacroRegistry",
    "get_macro_registry",
    "dynamic_spec_json_schema",
    "SYSTEM_PROMPT_INFINITE",
    "route_and_execute",
    "proxy_request",
    "validate_egress_url",
]
