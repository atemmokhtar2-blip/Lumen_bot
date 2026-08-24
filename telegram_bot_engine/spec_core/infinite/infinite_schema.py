"""DynamicBotSpec — infinite DAG of atomic flow nodes (Pydantic V2)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .atomic_primitives import (
    normalize_action_type,
    normalize_condition_type,
    ALLOWED_ACTIONS,
    ALLOWED_CONDITIONS,
    ALLOWED_TRANSFORMERS,
    ALLOWED_TRIGGERS,
    MAX_ACTIONS_PER_NODE,
    MAX_CONDITIONS_PER_NODE,
    MAX_NODES,
    MAX_TRANSFORMERS_PER_NODE,
)


class TriggerAtom(BaseModel):
    type: str
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def type_allowed(cls, v: str) -> str:
        t = (v or "").strip().lower()
        if t not in ALLOWED_TRIGGERS:
            raise ValueError(f"unsafe_or_unknown_trigger:{t}")
        return t


class ConditionAtom(BaseModel):
    type: str
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def type_allowed(cls, v: str) -> str:
        t = normalize_condition_type((v or "").strip().lower())
        if t not in ALLOWED_CONDITIONS and t not in {"state_equals"}:
            # after alias, must be in allowlist
            if t not in ALLOWED_CONDITIONS:
                raise ValueError(f"unsafe_or_unknown_condition:{v}")
        return t if t in ALLOWED_CONDITIONS else normalize_condition_type(v)


class ActionAtom(BaseModel):
    type: str
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def type_allowed(cls, v: str) -> str:
        t = normalize_action_type((v or "").strip().lower())
        if t not in ALLOWED_ACTIONS:
            raise ValueError(f"unsafe_or_unknown_action:{v}")
        return t


class TransformerAtom(BaseModel):
    type: str
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def type_allowed(cls, v: str) -> str:
        t = (v or "").strip().lower()
        if t not in ALLOWED_TRANSFORMERS:
            raise ValueError(f"unsafe_or_unknown_transformer:{t}")
        return t


class FlowNode(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    trigger: TriggerAtom
    conditions: list[ConditionAtom] = Field(default_factory=list)
    transformers: list[TransformerAtom] = Field(default_factory=list)
    actions: list[ActionAtom] = Field(default_factory=list)
    next_node_id: str | None = None

    @field_validator("id")
    @classmethod
    def id_safe(cls, v: str) -> str:
        s = (v or "").strip()
        if not s or not all(c.isalnum() or c in "_-" for c in s):
            raise ValueError("invalid_node_id")
        return s

    @model_validator(mode="after")
    def bounds(self) -> "FlowNode":
        if len(self.actions) > MAX_ACTIONS_PER_NODE:
            raise ValueError("too_many_actions_per_node")
        if len(self.conditions) > MAX_CONDITIONS_PER_NODE:
            raise ValueError("too_many_conditions_per_node")
        if len(self.transformers) > MAX_TRANSFORMERS_PER_NODE:
            raise ValueError("too_many_transformers_per_node")
        if not self.actions:
            raise ValueError("node_requires_at_least_one_action")
        return self


class DynamicBotSpec(BaseModel):
    """Infinite specification: DAG of atomic flow nodes."""

    bot_name: str = Field(default="infinite_bot", min_length=1, max_length=80)
    language: str = Field(default="ar", max_length=8)
    description: str = Field(default="", max_length=2000)
    nodes: list[FlowNode] = Field(default_factory=list)
    version: Literal["infinite_v1"] = "infinite_v1"

    @field_validator("bot_name")
    @classmethod
    def name_safe(cls, v: str) -> str:
        s = (v or "bot").strip()[:80]
        return s or "infinite_bot"

    @model_validator(mode="after")
    def structural_safety(self) -> "DynamicBotSpec":
        if not self.nodes:
            raise ValueError("nodes_empty")
        if len(self.nodes) > MAX_NODES:
            raise ValueError(f"too_many_nodes_max_{MAX_NODES}")
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_node_id")
        id_set = set(ids)
        for n in self.nodes:
            if n.next_node_id and n.next_node_id not in id_set:
                raise ValueError(f"dangling_next_node:{n.next_node_id}")
        return self
