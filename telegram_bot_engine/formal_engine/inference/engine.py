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
    if a in ("paid", "active", "enabled", "done", "completed", "is_admin", "banned",
             "passed", "verified", "locked"):
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
        "email": "أرسل البريد الإلكتروني",
        "grade": "أرسل الصف / المستوى",
        "phone": "أرسل رقم الهاتف",
        "city": "أرسل المدينة",
        "license": "أرسل رقم الرخصة",
        "plate": "أرسل رقم اللوحة",
        "type": "أرسل النوع",
        "title": "أرسل العنوان",
        "description": "أرسل الوصف",
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
        "student_id": "أرسل معرّف الطالب",
        "course_id": "أرسل رقم / كود الكورس",
        "nationality": "أرسل الجنسية",
        "company": "أرسل اسم الشركة",
        "capacity_kg": "أرسل السعة بالكيلو",
        "mileage": "أرسل قراءة العداد",
        "liters": "أرسل عدد اللترات",
        "cost": "أرسل التكلفة",
        "stops": "أرسل نقاط التوقف",
        "distance_km": "أرسل المسافة",
        "driver_id": "أرسل معرّف السائق",
        "room_id": "أرسل رقم الغرفة",
        "hotel_id": "أرسل الفندق",
        "progress": "أرسل نسبة التقدم",
        "price": "أرسل السعر",
    }

    # Arabic / English phrases in descriptions → field keys (text-grounded)
    _DESC_FIELD_MAP: list[tuple[str, str]] = [
        ("البريد", "email"), ("ايميل", "email"), ("email", "email"),
        ("الاسم", "name"), ("اسم", "name"), ("name", "name"),
        ("الصف", "grade"), ("المستوى", "grade"), ("grade", "grade"),
        ("الهاتف", "phone"), ("الجوال", "phone"), ("رقم الهاتف", "phone"), ("phone", "phone"),
        ("العنوان", "title"), ("title", "title"),
        ("الوصف", "description"), ("description", "description"),
        ("السعر", "price"), ("price", "price"),
        ("الكورس", "course_id"), ("رقم الكورس", "course_id"), ("كود الكورس", "course_id"),
        ("course", "course_id"), ("المادة", "course_id"),
        ("الطالب", "student_id"), ("student", "student_id"),
        ("المدينة", "city"), ("city", "city"),
        ("الدرجة", "score"), ("score", "score"),
        ("التقدم", "progress"), ("progress", "progress"),
        ("الملاحظات", "notes"), ("notes", "notes"),
        ("الكمية", "stock"), ("quantity", "stock"),
    ]

    def _prompt_for(field: str) -> str:
        f = field.lower()
        if f in _PROMPT:
            return _PROMPT[f]
        return f"أرسل {field}"

    def _fields_from_description(desc: str) -> list[str]:
        """Pull ordered field keys mentioned in the command description."""
        d = desc or ""
        if not d:
            return []
        found: list[str] = []
        seen: set[str] = set()
        # preserve order of appearance
        hits: list[tuple[int, str]] = []
        for phrase, key in _DESC_FIELD_MAP:
            idx = d.lower().find(phrase.lower()) if phrase.isascii() else d.find(phrase)
            if idx < 0:
                # try normalized arabic
                idx = d.find(phrase)
            if idx >= 0 and key not in seen:
                hits.append((idx, key))
                seen.add(key)
        hits.sort(key=lambda x: x[0])
        for _, key in hits:
            found.append(key)
        return found[:6]

    # Dynamic wizards from user commands + entities (no fixed domain map)
    _INPUT_VERBS = (
        "create", "add", "register", "book", "order", "submit", "new", "enroll",
        "open", "signup", "sign_up", "join", "apply", "insert", "post",
    )
    _SKIP_CMDS = {
        "cancel", "list", "admin", "stats", "broadcast", "ban", "help", "start",
        "show", "view", "get", "delete", "remove", "drop", "reject", "accept",
        "deliver", "arrive", "optimize", "report", "pay", "quiz", "score",
        "progress", "courses", "my_courses", "status", "info", "track",
        "available_orders", "search", "remind",
    }
    _SKIP_STEMS = (
        "cancel", "delete", "remove", "drop", "list", "stats", "admin",
        "broadcast", "ban", "available", "track", "search", "show", "view",
    )
    _DESC_INPUT_HINTS = (
        "يجمع", "اجمع", "يطلب", "اطلب", "يسجل", "تسجيل", "يحتاج", "ادخل",
        "أدخل", "enter", "collect", "gather", "ask for", "requires", "اسم",
        "بريد", "هاتف", "صف", "collects",
    )

    # Soft semantic hints: command/desc token → preferred entity stem
    _CMD_ENTITY_HINTS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
        (("register", "signup", "student", "طالب", "تسجيل"), ("student", "user", "member")),
        (("enroll", "join", "اشتراك", "تسجيل_كورس"), ("enrollment", "enrolment", "registration")),
        (("course", "كورس", "مادة"), ("course", "class", "subject")),
        (("order", "طلب", "شراء"), ("order", "purchase")),
        (("book", "حجز"), ("booking", "reservation", "appointment")),
        (("ticket", "تذكرة", "بلاغ"), ("ticket", "issue")),
        (("product", "منتج", "سلعة"), ("product", "item")),
        (("quiz", "اختبار"), ("quizattempt", "quiz", "attempt")),
    ]

    def _is_input_cmd(cname: str, desc: str = "") -> bool:
        """True only for collect/create style commands — never list/track/admin.
        Matching is token-based (snake_case parts), NOT raw substring, so
        'order' does not fire inside 'available_orders'.
        """
        c = cname.lower()
        if c in _SKIP_CMDS or c.startswith("my_"):
            return False
        parts = [p for p in c.replace("-", "_").split("_") if p]
        if any(s in parts for s in _SKIP_STEMS):
            return False
        # verb as whole path segment only
        if any(v in parts for v in _INPUT_VERBS):
            return True
        if any(c == v or c.startswith(v + "_") or c.endswith("_" + v) for v in _INPUT_VERBS):
            # still block if a skip stem is present (available_orders)
            if any(s in parts for s in _SKIP_STEMS):
                return False
            return True
        d = desc or ""
        if any(h in d for h in _DESC_INPUT_HINTS):
            # description says يجمع/يحتاج but command is list-like → still skip
            if any(s in parts for s in _SKIP_STEMS):
                return False
            return True
        return False

    def _entity_for_command(cmd_name: str, cmd_desc: str) -> str | None:
        """Match entity by name overlap + soft Arabic/English hints."""
        c = (cmd_name + " " + (cmd_desc or "")).lower().replace("_", " ")
        caps = [k for k in entity_fields if k and k[0].isupper()]
        best = None
        best_score = 0
        for ename in caps:
            score = 0
            el = ename.lower()
            if el in c.replace(" ", ""):
                score += 6
            for tok in re.findall(r"[a-z]{3,}", el):
                if tok in c:
                    score += 2
            if el.endswith("s") and el[:-1] in c:
                score += 3
            # soft hints — prefer entity whose stem matches command verb
            for triggers, stems in _CMD_ENTITY_HINTS:
                if any(t in c for t in triggers):
                    if any(s in el for s in stems):
                        score += 5
                    # stronger: command name itself is a stem of entity (enroll→Enrollment)
                    cn_only = cmd_name.lower().replace("_", "")
                    if any(cn_only and cn_only in s for s in stems) or any(
                        s.startswith(cn_only) or cn_only.startswith(s[: max(4, len(s) // 2)])
                        for s in stems if len(s) >= 4
                    ):
                        score += 4
            if score > best_score:
                best_score = score
                best = ename
        if best_score > 0:
            return best
        return None

    def _pick_wizard_fields(ent_name: str | None, desc: str) -> list[str]:
        """Prefer fields mentioned in description; else entity attrs (skip ids/flags)."""
        from_desc = _fields_from_description(desc)
        if from_desc:
            return from_desc
        if not ent_name:
            return []
        fields = entity_fields.get(ent_name) or entity_fields.get(ent_name.lower()) or []
        skip = {"id", "user_id", "banned", "paid", "active", "enabled", "passed", "verified", "locked"}
        return [f for f in fields if f.lower() not in skip][:6]

    for cmd in program.commands:
        cn = cmd.name
        desc = getattr(cmd, "description", "") or ""
        if not _is_input_cmd(cn, desc):
            continue
        ent_name = _entity_for_command(cn, desc)
        caps = [k for k in entity_fields if k and k[0].isupper()]
        if not ent_name and len(caps) == 1:
            ent_name = caps[0]
        # Prefer Enrollment entity for enroll/join even if Course also scored
        if cn.lower() in ("enroll", "join", "enrol"):
            for cand in caps:
                if "enroll" in cand.lower() or "registration" in cand.lower():
                    ent_name = cand
                    break
        fields = _pick_wizard_fields(ent_name, desc)
        # still no fields but description asks to collect → minimal name step
        if not fields and any(h in desc for h in _DESC_INPUT_HINTS):
            fields = _fields_from_description(desc) or ["name"]
        if not fields:
            continue
        steps = [{"key": f, "prompt": _prompt_for(f)} for f in fields]
        wizards.append({
            "id": cmd.name,
            "command": cmd.name,
            "entity": ent_name or "record",
            "steps": steps,
        })

    result.wizards = wizards

    # Ensure database flag when we have schemas/entities
    if result.schemas or program.entities:
        result.wants_database = True

    return result
