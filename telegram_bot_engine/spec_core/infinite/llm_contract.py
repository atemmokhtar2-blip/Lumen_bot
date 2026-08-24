"""Structured-output contract — EXACT architecture-plan atoms only."""
from __future__ import annotations

from typing import Any

from ..dynamic_bot_spec import (
    ALLOWED_ACTIONS,
    ALLOWED_CONDITIONS,
    ALLOWED_TRANSFORMERS,
    ALLOWED_TRIGGERS,
    MAX_NODES,
)

SYSTEM_PROMPT_INFINITE = f"""You are a deterministic bot-spec compiler.
You NEVER write Python or shell code.
You ONLY output a single JSON object: DynamicBotSpec.

Allowed triggers: {sorted(ALLOWED_TRIGGERS)}
Allowed conditions: {sorted(ALLOWED_CONDITIONS)}
Allowed actions: {sorted(ALLOWED_ACTIONS)}
Allowed transformers: {sorted(ALLOWED_TRANSFORMERS)}

Rules:
- Max {MAX_NODES} nodes. No cycles via next_node_id.
- Every node needs trigger + >=1 action.
- call_api URLs must be https:// (not localhost/private).
- Prefer on_command / on_message entry points.
"""


def dynamic_spec_json_schema() -> dict[str, Any]:
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
                                "type": {
                                    "type": "string",
                                    "enum": sorted(ALLOWED_TRIGGERS),
                                },
                                "config": {"type": "object"},
                            },
                        },
                        "conditions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["type"],
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": sorted(ALLOWED_CONDITIONS),
                                    },
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
                                    "type": {
                                        "type": "string",
                                        "enum": sorted(ALLOWED_TRANSFORMERS),
                                    },
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
                                    "type": {
                                        "type": "string",
                                        "enum": sorted(ALLOWED_ACTIONS),
                                    },
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
