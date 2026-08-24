"""DynamicBotSpec — EXACT architecture plan surface (atomic DAG).

This module is the authoritative infinite-spec model matching the published
architecture document:

  Trigger / Condition / Action / FlowNode / DynamicBotSpec
  + cycle detection + allowlisted actions only
  + max chain depth 15

Legacy capability BotSpec remains in schema.py for catalog generation.
Infinite path uses THIS model end-to-end: LLM JSON → validate → rule engine.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# --- Atoms EXACTLY as specified in the architecture plan ---

TriggerType = Literal["on_message", "on_command", "on_schedule", "on_webhook"]
ConditionType = Literal[
    "user_is_admin",
    "text_contains",
    "time_between",
    "state_equals",
]
ActionType = Literal[
    "send_message",
    "update_db",
    "call_api",
    "change_state",
]
TransformerType = Literal[
    "extract_regex",
    "translate_text",
    "summarize",
]

ALLOWED_TRIGGERS = frozenset({"on_message", "on_command", "on_schedule", "on_webhook"})
ALLOWED_CONDITIONS = frozenset(
    {"user_is_admin", "text_contains", "time_between", "state_equals"}
)
ALLOWED_ACTIONS = frozenset(
    {"send_message", "update_db", "call_api", "change_state"}
)
ALLOWED_TRANSFORMERS = frozenset(
    {"extract_regex", "translate_text", "summarize"}
)

MAX_NODES = 15
MAX_DAG_DEPTH = 15


class Trigger(BaseModel):
    type: TriggerType
    config: Dict[str, Any] = Field(default_factory=dict)


class Condition(BaseModel):
    type: ConditionType
    config: Dict[str, Any] = Field(default_factory=dict)


class Action(BaseModel):
    type: ActionType
    config: Dict[str, Any] = Field(default_factory=dict)


class Transformer(BaseModel):
    type: TransformerType
    config: Dict[str, Any] = Field(default_factory=dict)


class FlowNode(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    trigger: Trigger
    conditions: List[Condition] = Field(default_factory=list)
    transformers: List[Transformer] = Field(default_factory=list)
    actions: List[Action] = Field(min_length=1)
    next_node_id: Optional[str] = None

    @field_validator("id")
    @classmethod
    def _id_safe(cls, v: str) -> str:
        s = (v or "").strip()
        if not s or not all(c.isalnum() or c in "_-" for c in s):
            raise ValueError(f"invalid_node_id:{v}")
        return s


class DynamicBotSpec(BaseModel):
    """The Infinite Spec — DAG of atomic flow nodes."""

    bot_name: str = Field(min_length=1, max_length=80)
    nodes: List[FlowNode] = Field(min_length=1, max_length=MAX_NODES)
    language: str = Field(default="ar", max_length=8)
    description: str = Field(default="", max_length=2000)
    version: Literal["infinite_v1"] = "infinite_v1"

    @model_validator(mode="after")
    def prevent_infinite_loops_and_unsafe_actions(self) -> "DynamicBotSpec":
        # Unique ids
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Infinite loop / duplicate node id detected")

        id_set = set(ids)
        for node in self.nodes:
            if node.next_node_id and node.next_node_id not in id_set:
                raise ValueError(f"dangling_next_node:{node.next_node_id}")
            for action in node.actions:
                if action.type not in ALLOWED_ACTIONS:
                    raise ValueError(f"Non-deterministic/Unsafe action: {action.type}")
            for cond in node.conditions:
                if cond.type not in ALLOWED_CONDITIONS:
                    raise ValueError(f"Unsafe condition: {cond.type}")
            if node.trigger.type not in ALLOWED_TRIGGERS:
                raise ValueError(f"Unsafe trigger: {node.trigger.type}")

        # Proper cycle detection (DFS) — stronger than id-only check in the plan example
        graph = {n.id: n.next_node_id for n in self.nodes}
        color: dict[str, int] = {i: 0 for i in id_set}  # 0 white 1 gray 2 black

        def dfs(u: str) -> None:
            color[u] = 1
            v = graph.get(u)
            if v:
                if color.get(v) == 1:
                    raise ValueError(f"Infinite loop detected at node: {u}->{v}")
                if color.get(v) == 0:
                    dfs(v)
            color[u] = 2

        for nid in id_set:
            if color[nid] == 0:
                dfs(nid)

        # Max chain depth
        memo: dict[str, int] = {}

        def depth(u: str, stack: set[str]) -> int:
            if u in stack:
                return 0
            if u in memo:
                return memo[u]
            nxt = graph.get(u)
            if not nxt or nxt not in graph:
                memo[u] = 1
                return 1
            stack.add(u)
            d = 1 + depth(nxt, stack)
            stack.discard(u)
            memo[u] = d
            return d

        max_d = max((depth(n.id, set()) for n in self.nodes), default=0)
        if max_d > MAX_DAG_DEPTH:
            raise ValueError(f"DAG depth exceeded: {max_d}>{MAX_DAG_DEPTH}")

        return self


def parse_dynamic_spec(data: dict[str, Any] | DynamicBotSpec) -> DynamicBotSpec:
    if isinstance(data, DynamicBotSpec):
        return data
    return DynamicBotSpec.model_validate(data)
