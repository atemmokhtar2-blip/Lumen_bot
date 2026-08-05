"""
Custom DSL AST — intermediate language for Relations & Operations.

Example form:
  Entity(Appointment) -> Requires(User, Time) -> Action(ValidateAvailability)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EntityNode:
    """Entity(Name)"""
    name: str
    attributes: list[str] = field(default_factory=list)


@dataclass
class RequiresNode:
    """Requires(A, B, ...)"""
    operands: list[str] = field(default_factory=list)


@dataclass
class ActionNode:
    """Action(Name)"""
    name: str
    args: list[str] = field(default_factory=list)


@dataclass
class RelationNode:
    """
    Chain: Entity(...) -> Requires(...) -> Action(...)
    """
    entity: EntityNode | None = None
    requires: RequiresNode | None = None
    action: ActionNode | None = None
    raw: str = ""


@dataclass
class OperationNode:
    """
    Logical operation derived from text:
      - loop       (repetition)
      - decision   (branch / decision tree)
      - store      (persistence / schema)
      - compute    (pure calculation)
      - emit       (output / reply)
      - receive    (input / command / button)
    """
    kind: str
    name: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    body_refs: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class DSLProgram:
    """Full intermediate program: relations + operations."""
    relations: list[RelationNode] = field(default_factory=list)
    operations: list[OperationNode] = field(default_factory=list)
    entities: list[EntityNode] = field(default_factory=list)
    source_hash: str = ""
