"""
Custom DSL AST — Relations, Operations, and deep Rules (conditional/compute).
No domain templates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EntityNode:
    name: str
    attributes: list[str] = field(default_factory=list)
    attr_types: dict[str, str] = field(default_factory=dict)


@dataclass
class RequiresNode:
    operands: list[str] = field(default_factory=list)


@dataclass
class ActionNode:
    name: str
    args: list[str] = field(default_factory=list)


@dataclass
class RelationNode:
    entity: EntityNode | None = None
    requires: RequiresNode | None = None
    action: ActionNode | None = None
    raw: str = ""


@dataclass
class CommandNode:
    name: str
    description: str = ""
    admin_only: bool = False


@dataclass
class ButtonNode:
    label: str
    callback_id: str = ""


@dataclass
class OperationNode:
    kind: str
    name: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    body_refs: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


# ── Deep rules (conditional / compute / effect) ───────────────────────────

@dataclass
class ConditionExpr:
    """Atomic condition extracted from text."""
    left: str          # field / signal / choice
    op: str            # eq | ne | gt | gte | lt | lte | contains | truthy
    right: str = ""    # literal or field
    raw: str = ""


@dataclass
class EffectExpr:
    """Effect to apply when condition holds (or always for compute)."""
    kind: str          # set | create | reply | goto | call | accumulate | enable
    target: str = ""   # field / entity / step / action
    value: str = ""
    raw: str = ""


@dataclass
class RuleNode:
    """
    Conditional or compute rule:
      IF condition(s) THEN effect(s)
      OR pure compute: score = f(...)
    """
    name: str
    kind: str  # conditional | compute | threshold | sequence
    conditions: list[ConditionExpr] = field(default_factory=list)
    effects: list[EffectExpr] = field(default_factory=list)
    raw: str = ""


@dataclass
class DSLProgram:
    relations: list[RelationNode] = field(default_factory=list)
    operations: list[OperationNode] = field(default_factory=list)
    entities: list[EntityNode] = field(default_factory=list)
    commands: list[CommandNode] = field(default_factory=list)
    buttons: list[ButtonNode] = field(default_factory=list)
    rules: list[RuleNode] = field(default_factory=list)
    source_hash: str = ""
    wants_database: bool = False
    wants_files: bool = False
