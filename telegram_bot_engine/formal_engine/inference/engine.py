"""
Inference Engine.

Rules (as specified):
  - إذا كان هناك "تكرار"   → حلقات (Loops)
  - إذا كان هناك "قرار"    → أشجار شرطية (Decision Trees)
  - إذا كان هناك "تخزين"   → مخطط قاعدة بيانات فريد (unique Schema)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..dsl.ast import DSLProgram, EntityNode, OperationNode, RelationNode


@dataclass
class LoopPlan:
    name: str
    iterable: str
    body_ops: list[str] = field(default_factory=list)


@dataclass
class DecisionPlan:
    name: str
    discriminant: str
    branches: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SchemaPlan:
    """Unique schema — not a generic table."""
    table: str
    columns: list[tuple[str, str]] = field(default_factory=list)  # (name, py_type)
    primary_key: str = "id"


@dataclass
class InferenceResult:
    loops: list[LoopPlan] = field(default_factory=list)
    decisions: list[DecisionPlan] = field(default_factory=list)
    schemas: list[SchemaPlan] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    receives: list[str] = field(default_factory=list)
    emits: list[str] = field(default_factory=list)
    compute_steps: list[dict[str, Any]] = field(default_factory=list)
    relations: list[RelationNode] = field(default_factory=list)
    entities: list[EntityNode] = field(default_factory=list)


def _schema_from_entity(e: EntityNode, rels: list[RelationNode]) -> SchemaPlan:
    cols: list[tuple[str, str]] = [("id", "str")]
    seen = {"id"}
    # attributes on entity
    for a in e.attributes:
        if a and a not in seen:
            seen.add(a)
            cols.append((a, "str"))
    # requires operands become columns
    for r in rels:
        if r.entity and r.entity.name.lower() == e.name.lower() and r.requires:
            for op in r.requires.operands:
                if op and op not in seen:
                    seen.add(op)
                    cols.append((op, "str"))
    # structural user link when entity is not User
    if e.name.lower() != "user" and "user_id" not in seen:
        cols.append(("user_id", "int"))
    return SchemaPlan(table=e.name.lower(), columns=cols, primary_key="id")


def infer(program: DSLProgram) -> InferenceResult:
    """Apply formal inference rules on DSLProgram → structural plans."""
    result = InferenceResult(
        relations=list(program.relations),
        entities=list(program.entities),
    )

    # Index operations by kind
    by_kind: dict[str, list[OperationNode]] = {}
    for op in program.operations:
        by_kind.setdefault(op.kind, []).append(op)

    # Rule: repetition → Loops
    for op in by_kind.get("loop", []):
        result.loops.append(
            LoopPlan(
                name=op.name,
                iterable=(op.inputs[0] if op.inputs else "items"),
                body_ops=list(op.body_refs),
            )
        )

    # Rule: decision → Decision Trees
    for op in by_kind.get("decision", []):
        branches = []
        # pull branch labels from compute steps meta if present
        for c in by_kind.get("compute", []):
            label = (c.meta or {}).get("label") or ""
            if any(k in label for k in ("إذا", "لو", "if ", "اختيار")):
                branches.append({"label": label[:80], "target": c.name})
        if not branches:
            branches = [
                {"label": "branch_a", "target": "path_a"},
                {"label": "branch_b", "target": "path_b"},
            ]
        result.decisions.append(
            DecisionPlan(
                name=op.name,
                discriminant=(op.inputs[0] if op.inputs else "choice"),
                branches=branches,
            )
        )

    # Rule: storage → unique Schema (per entity, not generic table)
    store_ops = by_kind.get("store", [])
    if store_ops or program.entities:
        for e in program.entities:
            result.schemas.append(_schema_from_entity(e, program.relations))
        # if storage signaled but no entities, synthesize one schema from relation requires
        if not result.schemas and store_ops:
            cols = [("id", "str"), ("user_id", "int"), ("payload", "str")]
            result.schemas.append(SchemaPlan(table="record", columns=cols))

    # Actions from relations
    for r in program.relations:
        if r.action and r.action.name:
            result.actions.append(r.action.name)

    # receive / emit
    for op in by_kind.get("receive", []):
        result.receives.append(op.name)
    for op in by_kind.get("emit", []):
        result.emits.append(op.name)

    # sequential compute steps
    for op in by_kind.get("compute", []):
        result.compute_steps.append(
            {
                "name": op.name,
                "label": (op.meta or {}).get("label", op.name),
                "ordinal": (op.meta or {}).get("ordinal", 0),
                "inputs": list(op.inputs),
                "outputs": list(op.outputs),
            }
        )
    result.compute_steps.sort(key=lambda x: x.get("ordinal") or 0)

    return result
