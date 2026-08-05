"""
Inference Engine — loops, decision trees, unique schemas, deep rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..dsl.ast import (
    ButtonNode,
    CommandNode,
    DSLProgram,
    EntityNode,
    OperationNode,
    RelationNode,
    RuleNode,
)


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
    table: str
    columns: list[tuple[str, str]] = field(default_factory=list)
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
    commands: list[CommandNode] = field(default_factory=list)
    buttons: list[ButtonNode] = field(default_factory=list)
    rules: list[RuleNode] = field(default_factory=list)
    wants_database: bool = False
    wants_files: bool = False


def _col_type(name: str, hinted: str | None = None) -> str:
    if hinted in ("int", "bool", "str", "float"):
        return hinted
    a = (name or "").lower()
    if a == "user_id":
        return "int"
    if a in ("price", "amount", "score", "qty", "quantity", "stock", "duration",
             "duration_min", "duration_weeks", "level", "count", "total", "progress"):
        return "int"
    if a in ("paid", "active", "enabled", "done", "completed", "is_admin"):
        return "bool"
    return "str"


def _schema_from_entity(e: EntityNode, rels: list[RelationNode]) -> SchemaPlan:
    cols: list[tuple[str, str]] = [("id", "str")]
    seen = {"id"}
    for a in e.attributes:
        if a and a not in seen:
            seen.add(a)
            cols.append((a, _col_type(a, (e.attr_types or {}).get(a))))
    for r in rels:
        if r.entity and r.entity.name.lower() == e.name.lower() and r.requires:
            for op in r.requires.operands:
                if op and op not in seen:
                    seen.add(op)
                    cols.append((op, _col_type(op)))
    if e.name.lower() not in ("user", "student") and "user_id" not in seen:
        cols.append(("user_id", "int"))
    return SchemaPlan(table=e.name.lower(), columns=cols, primary_key="id")


def infer(program: DSLProgram) -> InferenceResult:
    result = InferenceResult(
        relations=list(program.relations),
        entities=list(program.entities),
        commands=list(program.commands),
        buttons=list(program.buttons),
        rules=list(program.rules),
        wants_database=bool(program.wants_database),
        wants_files=bool(program.wants_files),
    )

    by_kind: dict[str, list[OperationNode]] = {}
    for op in program.operations:
        by_kind.setdefault(op.kind, []).append(op)

    for op in by_kind.get("loop", []):
        result.loops.append(
            LoopPlan(name=op.name, iterable=(op.inputs[0] if op.inputs else "items"), body_ops=list(op.body_refs))
        )

    for op in by_kind.get("decision", []):
        branches = list((op.meta or {}).get("branches") or [])
        if not branches and program.buttons:
            branches = [{"label": b.label, "target": b.callback_id} for b in program.buttons]
        # enrich branches from choice rules
        for rule in program.rules:
            if rule.kind != "conditional":
                continue
            for c in rule.conditions:
                if c.left == "choice" and c.right:
                    target = c.right
                    for e in rule.effects:
                        if e.kind == "goto" and e.target:
                            target = e.target
                            break
                    branches.append({"label": c.right, "target": target})
        # dedupe by label
        seen_l: set[str] = set()
        uniq = []
        for b in branches:
            lab = str(b.get("label") or "")
            if lab and lab not in seen_l:
                seen_l.add(lab)
                uniq.append(b)
        if not uniq:
            uniq = [{"label": "branch_a", "target": "path_a"}, {"label": "branch_b", "target": "path_b"}]
        result.decisions.append(
            DecisionPlan(name=op.name, discriminant=(op.inputs[0] if op.inputs else "choice"), branches=uniq)
        )

    # if rules exist but no decision op, still build decision from choice rules
    if not result.decisions:
        branches = []
        for rule in program.rules:
            for c in rule.conditions:
                if c.left == "choice" and c.right:
                    branches.append({"label": c.right, "target": c.right})
        if program.buttons:
            for b in program.buttons:
                branches.append({"label": b.label, "target": b.callback_id})
        if branches:
            result.decisions.append(DecisionPlan(name="BranchOnChoice", discriminant="choice", branches=branches))

    store_ops = by_kind.get("store", [])
    if store_ops or program.entities:
        for e in program.entities:
            result.schemas.append(_schema_from_entity(e, program.relations))
        if not result.schemas and store_ops:
            result.schemas.append(SchemaPlan(table="record", columns=[("id", "str"), ("user_id", "int"), ("payload", "str")]))

    for r in program.relations:
        if r.action and r.action.name:
            result.actions.append(r.action.name)

    for op in by_kind.get("receive", []):
        result.receives.append(op.name)
    for op in by_kind.get("emit", []):
        result.emits.append(op.name)

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
