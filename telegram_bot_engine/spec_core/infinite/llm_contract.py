"""Structured-output contract for LLM → DynamicBotSpec (no free-form Python)."""
from __future__ import annotations

from typing import Any

from .atomic_primitives import (
    ALLOWED_ACTIONS,
    ALLOWED_CONDITIONS,
    ALLOWED_TRANSFORMERS,
    ALLOWED_TRIGGERS,
    MAX_NODES,
)


SYSTEM_PROMPT_INFINITE = f"""You are a deterministic bot-spec compiler.
You NEVER write Python or shell code.
You ONLY output a single JSON object matching DynamicBotSpec (infinite_v1).

Allowed trigger types: {sorted(ALLOWED_TRIGGERS)}
Allowed condition types: {sorted(ALLOWED_CONDITIONS)}
Allowed action types: {sorted(ALLOWED_ACTIONS)}
Allowed transformer types: {sorted(ALLOWED_TRANSFORMERS)}

Rules:
- Max {MAX_NODES} nodes. No cycles in next_node_id chains.
- Every node needs >=1 action.
- call_external_api URLs must be https:// and not private/localhost.
- Prefer on_command / on_start / on_message entry points.
- Language of user-facing message text should match the user request.
"""


def dynamic_spec_json_schema() -> dict[str, Any]:
    """JSON Schema fragment for function-calling / structured outputs."""
    return {
        "type": "object",
        "required": ["bot_name", "nodes"],
        "properties": {
            "bot_name": {"type": "string"},
            "language": {"type": "string"},
            "description": {"type": "string"},
            "version": {"type": "string", "enum": ["infinite_v1"]},
            "nodes": {
                "type": "array",
                "maxItems": MAX_NODES,
                "items": {
                    "type": "object",
                    "required": ["id", "trigger", "actions"],
                    "properties": {
                        "id": {"type": "string"},
                        "trigger": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {
                                "type": {"type": "string", "enum": sorted(ALLOWED_TRIGGERS)},
                                "config": {"type": "object"},
                            },
                        },
                        "conditions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["type"],
                                "properties": {
                                    "type": {"type": "string", "enum": sorted(ALLOWED_CONDITIONS)},
                                    "config": {"type": "object"},
                                },
                            },
                        },
                        "transformers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["type"],
                                "properties": {
                                    "type": {"type": "string", "enum": sorted(ALLOWED_TRANSFORMERS)},
                                    "config": {"type": "object"},
                                },
                            },
                        },
                        "actions": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "required": ["type"],
                                "properties": {
                                    "type": {"type": "string", "enum": sorted(ALLOWED_ACTIONS)},
                                    "config": {"type": "object"},
                                },
                            },
                        },
                        "next_node_id": {"type": ["string", "null"]},
                    },
                },
            },
        },
    }
