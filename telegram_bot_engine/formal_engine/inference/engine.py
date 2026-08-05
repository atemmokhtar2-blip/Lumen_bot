"""
Inference Engine — loops, decision trees, unique schemas, deep rules.
"""

from __future__ import annotations
import re

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
    wizards: list[dict[str, Any]] = field(default_factory=list)
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

    # Multi-screen wizards: command → ordered field prompts from entity attrs
    wizards: list[dict] = []
    entity_fields: dict[str, list[str]] = {}
    for e in program.entities:
        fields = []
        for a in (e.attributes or []):
            name = a if isinstance(a, str) else getattr(a, "name", str(a))
            name = str(name).strip()
            if name and name.lower() not in ("id", "user_id", "status", "available", "paid", "active", "enabled"):
                fields.append(name)
        if fields:
            entity_fields[e.name] = fields
            entity_fields[e.name.lower()] = fields

    # Arabic prompt labels for common fields
    _PROMPT = {
        "origin": "أرسل المنشأ / نقطة الانطلاق",
        "destination": "أرسل الوجهة",
        "weight": "أرسل الوزن (رقم)",
        "amount": "أرسل المبلغ (رقم)",
        "name": "أرسل الاسم",
        "phone": "أرسل رقم الهاتف",
        "city": "أرسل المدينة",
        "license": "أرسل رقم الرخصة",
        "plate": "أرسل رقم اللوحة",
        "type": "أرسل النوع",
        "title": "أرسل العنوان",
        "code": "أرسل الكود",
        "topic": "أرسل موضوع الشكوى",
        "body": "أكتب نص الشكوى",
        "comment": "أكتب تعليقك",
        "rating": "أرسل التقييم من 1 إلى 5",
        "score": "أرسل الدرجة",
        "status": "أرسل الحالة",
        "check_in": "أرسل تاريخ الوصول",
        "check_out": "أرسل تاريخ المغادرة",
        "slot": "أرسل الموعد/الوقت",
        "notes": "أرسل ملاحظاتك",
        "items": "أرسل عناصر الطلب",
        "sku": "أرسل رمز الصنف",
        "stock": "أرسل الكمية",
        "issue": "صف المشكلة",
        "severity": "أرسل مستوى الخطورة (رقم)",
        "faculty": "أرسل الكلية",
        "year": "أرسل السنة",
        "student_id": "أرسل الرقم الجامعي",
        "nationality": "أرسل الجنسية",
        "company": "أرسل اسم الشركة",
        "capacity_kg": "أرسل السعة بالكيلو",
        "mileage": "أرسل قراءة العداد",
        "liters": "أرسل عدد اللترات",
        "cost": "أرسل التكلفة",
        "stops": "أرسل نقاط التوقف",
        "distance_km": "أرسل المسافة",
        "driver_id": "أرسل معرّف السائق",
        "course_id": "أرسل كود المادة",
        "room_id": "أرسل رقم الغرفة",
        "hotel_id": "أرسل الفندق",
    }

    def _prompt_for(field: str) -> str:
        f = field.lower()
        if f in _PROMPT:
            return _PROMPT[f]
        return f"أرسل {field}"

    # Dynamic wizards from user commands + entities (no fixed domain map)
    # Only "input" commands: create/add/register/book/order/submit — never cancel/list/admin
    _INPUT_VERBS = ("create", "add", "register", "book", "order", "submit", "new", "enroll", "open")
    _SKIP_VERBS = ("cancel", "list", "my_", "admin", "stats", "broadcast", "ban", "help", "start",
                   "show", "view", "get", "delete", "remove", "drop", "reject", "accept", "deliver",
                   "arrive", "optimize", "report", "set_price", "pay")  # pay may be simple amount-only

    def _is_input_cmd(cname: str) -> bool:
        c = cname.lower()
        if any(c.startswith(s) or f"_{s}" in f"_{c}" for s in _SKIP_VERBS if s.endswith("_") or s in ("my_",)):
            if c.startswith("my_") or c in ("admin", "stats", "help", "start", "broadcast", "ban"):
                return False
        if any(s in c for s in ("cancel", "delete", "remove", "drop", "reject", "accept", "list", "stats", "admin", "broadcast", "ban", "help", "start", "my_", "optimize", "report")):
            return False
        if any(v in c for v in _INPUT_VERBS):
            return True
        # command description may signal input
        return False

    def _entity_for_command(cmd_name: str, cmd_desc: str) -> str | None:
        """Match entity by name overlap with command — fully from declared entities."""
        c = (cmd_name + " " + (cmd_desc or "")).lower().replace("_", " ")
        best = None
        best_score = 0
        for ename, fields in entity_fields.items():
            if ename != ename:  # noqa — keep lower keys skipped
                continue
            # only canonical Capitalized names
            if not ename or ename[0].islower():
                continue
            score = 0
            el = ename.lower()
            if el in c.replace(" ", ""):
                score += 5
            # token overlap
            for tok in re.findall(r"[a-z]{3,}", el):
                if tok in c:
                    score += 2
            # singular/plural rough
            if el.endswith("s") and el[:-1] in c:
                score += 3
            if score > best_score:
                best_score = score
                best = ename
        return best if best_score > 0 else None

    for cmd in program.commands:
        cn = cmd.name
        if not _is_input_cmd(cn):
            continue
        desc = getattr(cmd, "description", "") or ""
        ent_name = _entity_for_command(cn, desc)
        # fallback: first entity if only one and create-like
        if not ent_name and len([k for k in entity_fields if k and k[0].isupper()]) == 1:
            ent_name = next(k for k in entity_fields if k and k[0].isupper())
        if not ent_name:
            continue
        fields = entity_fields.get(ent_name) or entity_fields.get(ent_name.lower()) or []
        if not fields:
            continue
        fields = fields[:6]
        steps = [{"key": f, "prompt": _prompt_for(f)} for f in fields]
        wizards.append({
            "id": cmd.name,
            "command": cmd.name,
            "entity": ent_name,
            "steps": steps,
        })


    result.wizards = wizards

    return result
