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
    defensive_tools: list[str] = field(default_factory=list)
    dynamic_tools: list[dict] = field(default_factory=list)
    source_text: str = ""


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
    # Keep schema strictly from declared attributes — no forced user_id template
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
        "name": "أرسل الاسم",
        "phone": "أرسل رقم الهاتف",
        "address": "أرسل العنوان",
        "email": "أرسل البريد الإلكتروني",
        "status": "أرسل الحالة",
        "date": "أرسل التاريخ",
        "time": "أرسل الوقت",
        "city": "أرسل المدينة",
        "notes": "أرسل الملاحظات",
        "description": "أرسل الوصف",
        "quantity": "أرسل الكمية",
        "title": "أرسل العنوان/الاسم",
        "id": "أرسل رقم / معرّف التتبع",
        "domain": "أدخل الدومين (example.com):",
        "url": "أدخل رابط الموقع (https://...):",
        "target": "أدخل الهدف للفحص:",
        "project": "أدخل اسم المشروع:",
        "author": "أرسل اسم المؤلف:",
        "isbn": "أرسل ISBN:",
        "due_date": "أرسل تاريخ الإرجاع:",
        "book_id": "أرسل اسم أو رقم الكتاب:",
        "title": "أرسل العنوان:",
    }


    # Linguistic field cues extracted from user wording only (not bot templates).
    # Maps surface words that appear in the user's text → stable field keys.
    _DESC_FIELD_MAP: list[tuple[str, str]] = [
        ("البريد الإلكتروني", "email"), ("البريد", "email"), ("ايميل", "email"), ("email", "email"),
        ("اسم المريض", "patient_name"), ("patient_name", "patient_name"), ("patient name", "patient_name"),
        ("الاسم", "name"), ("اسم", "name"), ("name", "name"),
        ("رقم الهاتف", "phone"), ("الهاتف", "phone"), ("الجوال", "phone"), ("phone", "phone"),
        ("العنوان", "address"), ("address", "address"),
        ("الوصف", "description"), ("description", "description"),
        ("العنوان/الاسم", "title"), ("title", "title"),
        ("التاريخ", "date"), ("تاريخ", "date"), ("date", "date"),
        ("الوقت", "time"), ("وقت", "time"), ("time", "time"),
        ("الموعد", "slot"), ("موعد", "slot"), ("slot", "slot"),
        ("الحالة", "status"), ("status", "status"),
        ("الملاحظات", "notes"), ("ملاحظات", "notes"), ("notes", "notes"),
        ("السعر", "price"), ("price", "price"),
        ("الكمية", "quantity"), ("كمية", "quantity"), ("quantity", "quantity"),
        ("المدينة", "city"), ("city", "city"),
        ("الدرجة", "score"), ("score", "score"),
        ("التقدم", "progress"), ("progress", "progress"),
        ("الصف", "grade"), ("المستوى", "grade"), ("grade", "grade"),
        ("الكورس", "course_id"), ("رقم الكورس", "course_id"), ("course", "course_id"),
        ("الطالب", "student_id"), ("student", "student_id"),
    ]

    def _prompt_for(field: str) -> str:
        f = (field or "").strip()
        fl = f.lower()
        # Prefer Arabic cue that the user actually used in nearby text when available
        for phrase, key in _DESC_FIELD_MAP:
            if key == fl or key == f:
                # Use the first Arabic phrase for this key if any
                if any("\u0600" <= ch <= "\u06FF" for ch in phrase):
                    return f"أرسل {phrase}"
        if fl in _PROMPT:
            return _PROMPT[fl]
        # Dynamic: humanize snake_case from user-derived key only
        label = f.replace("_", " ").strip()
        return f"أرسل {label}"

    def _split_field_chunk(chunk: str) -> list[str]:
        """Split a user-written list of fields into ordered keys."""
        import re as _re
        chunk = (chunk or "").strip()
        if not chunk:
            return []
        # normalize conjunctions
        chunk = _re.sub(r"\s+و\s+", ",", chunk)
        chunk = _re.sub(r"\s+and\s+", ",", chunk, flags=_re.I)
        parts = _re.split(r"[\s,،/|+\-]+", chunk)
        keys: list[str] = []
        seen: set[str] = set()
        for p in parts:
            p = p.strip().strip("()[]«»\"'")
            if len(p) < 2:
                continue
            # map known linguistic cue
            mapped = None
            for phrase, key in _DESC_FIELD_MAP:
                if p == phrase or p.lower() == phrase.lower() or phrase in p:
                    mapped = key
                    break
            if mapped is None:
                # ascii identifier from user token
                ident = _re.sub(r"[^a-zA-Z0-9_]", "_", p)
                if ident and ident[0].isdigit():
                    ident = "f_" + ident
                if not ident or len(ident) < 2:
                    continue
                # skip pure stop words
                if ident.lower() in {
                    "the", "a", "an", "id", "user_id", "and", "or",
                    "new", "جديد", "فقط", "only", "for", "to", "from",
                }:
                    continue
                # Drop pure underscore / non-alnum noise
                if not any(ch.isalnum() for ch in ident):
                    continue
                mapped = ident.lower()
            if mapped not in seen:
                seen.add(mapped)
                keys.append(mapped)
        return keys[:8]

    def _fields_from_description(desc: str) -> list[str]:
        """Pull ordered field keys evidenced in the command description text only."""
        import re as _re
        d = desc or ""
        if not d:
            return []
        found: list[str] = []
        seen: set[str] = set()

        def _push(keys: list[str]) -> None:
            for k in keys:
                if k and k not in seen:
                    seen.add(k)
                    found.append(k)

        explicit = False
        # 1) Parenthetical / bracket lists: (الاسم والتاريخ والوقت)
        for m in _re.finditer(r"[\(\[«]([^\)\]»]{2,100})[\)\]»]", d):
            keys = _split_field_chunk(m.group(1))
            if keys:
                _push(keys)
                explicit = True

        # 2) After collect verbs
        for m in _re.finditer(
            r"(?:يجمع|اجمع|يطلب|اطلب|يحتاج|جمع|collect(?:s)?|gather(?:s)?|ask(?:s)?\s+for)\s+([^\n\.]{3,100})",
            d,
            _re.I,
        ):
            keys = _split_field_chunk(m.group(1))
            if keys:
                _push(keys)
                explicit = True

        # 3) Fallback scan only when no explicit list
        if not explicit:
            hits: list[tuple[int, str]] = []
            for phrase, key in _DESC_FIELD_MAP:
                if key in seen:
                    continue
                idx = d.lower().find(phrase.lower()) if phrase.isascii() else d.find(phrase)
                if idx >= 0:
                    hits.append((idx, key))
                    seen.add(key)
            hits.sort(key=lambda x: x[0])
            for _, key in hits:
                if key not in found:
                    found.append(key)

        noise = {
            "new", "id", "user_id", "and", "or", "the", "a",
            "____", "__", "_", "status", "registered_at", "created_at", "updated_at",
            "is_admin", "banned", "active", "enabled",
        }
        found = [
            k for k in found
            if k and any(ch.isalnum() for ch in k)
            and k.lower() not in noise
            and not set(k) <= {"_"}
        ]
        return found[:8]


    _INPUT_VERBS = (
        "create", "add", "register", "submit", "new", "book", "order",
        "open", "signup", "sign_up", "join", "apply", "insert", "post",
        "request", "form", "subscribe", "invite",
        "scan", "inspect", "analyze", "audit",
    )
    _LOOKUP_CMDS = {
        "track", "search", "status", "info", "find", "lookup", "check", "query",
    }
    _MINE_PREFIX = ("my_",)
    _MINE_CMDS = {
        "progress", "score", "history", "balance", "profile", "settings",
    }
    _LIST_CMDS = {
        "list", "menu", "items", "stats", "statistics", "dashboard",
    }
    _SKIP_CMDS = {
        "cancel", "admin", "broadcast", "ban", "help", "start",
        "show", "view", "get", "delete", "remove", "drop", "reject", "accept",
        "deliver", "arrive", "optimize", "pay", "quiz",
        "remind", "confirm", "notifications",
    }
    _SKIP_STEMS = (
        "cancel", "delete", "remove", "drop", "stats", "admin",
        "broadcast", "ban", "available", "show", "view",
    )
    _DESC_INPUT_HINTS = (
        "يجمع", "اجمع", "يطلب", "اطلب", "يسجل", "تسجيل", "يحتاج", "ادخل",
        "أدخل", "enter", "collect", "gather", "ask for", "requires", "اسم",
        "بريد", "هاتف", "صف", "collects", "حجز", "طلب", "موعد", "تاريخ", "وقت",
    )

    def _cmd_kind(cname: str, desc: str = "") -> str:
        c = cname.lower()
        if c in _SKIP_CMDS:
            return "skip"
        parts = [p for p in c.replace("-", "_").split("_") if p]
        # Multi-part commands like cancel_appointment are not pure skip stems
        if len(parts) == 1 and any(s in parts for s in _SKIP_STEMS) and c not in _LOOKUP_CMDS:
            return "skip"
        if c in _LOOKUP_CMDS or any(x in parts for x in ("track", "search", "find", "lookup")):
            return "lookup"
        if c.startswith(_MINE_PREFIX) or c in _MINE_CMDS:
            return "mine"
        if c in _LIST_CMDS or any(x in parts for x in ("list", "menu", "catalog")):
            return "list"
        if any(v in parts for v in _INPUT_VERBS):
            return "collect"
        if any(c == v or c.startswith(v + "_") or c.endswith("_" + v) for v in _INPUT_VERBS):
            return "collect"
        d = desc or ""
        if any(h in d for h in _DESC_INPUT_HINTS):
            return "collect"
        return "action"

    def _entity_for_command(cmd_name: str, cmd_desc: str) -> str | None:
        """Bind command to an entity that already exists in the user contract only."""
        cn = (cmd_name or "").lower().replace("-", "_")
        cd = (cmd_desc or "")
        cd_l = cd.lower()
        desc_fields = set(_fields_from_description(cd))
        best, best_score = None, 0
        non_user = [e for e in entity_fields if e.lower() not in {"user", "admin", "users"}]

        for ename, fields in entity_fields.items():
            el = ename.lower()
            fl_set = {str(f).lower() for f in (fields or [])}
            score = 0
            if el in cn or cn.endswith("_" + el) or cn.startswith(el + "_"):
                score += 10
            if el in cd_l:
                score += 6
            for part in el.replace("-", "_").split("_"):
                if len(part) >= 3 and part in cn.split("_"):
                    score += 6
            cn_only = cn.replace("_", "")
            if cn_only and (cn_only in el or el in cn_only):
                score += 3
            # Field overlap between description cues and entity attributes (text-grounded)
            overlap = len(desc_fields & fl_set)
            score += overlap * 5
            # Arabic soft cues that appear in BOTH description and entity name fragments
            if any(w in cd for w in ("موعد", "حجز", "appointment", "booking")) and any(
                w in el for w in ("appoint", "booking", "reservation", "slot")
            ):
                score += 8
            if any(w in cd for w in ("طلب", "order")) and any(w in el for w in ("order", "request")):
                score += 6
            if score > best_score:
                best_score = score
                best = ename

        # Collect commands with no name match: prefer the single non-User entity in the contract
        if best_score == 0 and len(non_user) == 1:
            return non_user[0]
        # Prefer non-User when scores tie-ish and description mentions collect verbs
        if best and best.lower() in {"user", "users"} and non_user and desc_fields:
            alt_scores = []
            for ename in non_user:
                fl_set = {str(f).lower() for f in (entity_fields.get(ename) or [])}
                alt_scores.append((len(desc_fields & fl_set), ename))
            alt_scores.sort(reverse=True)
            if alt_scores and alt_scores[0][0] > 0:
                return alt_scores[0][1]
        return best if best_score > 0 else None

    def _pick_wizard_fields(ent_name: str | None, desc: str, kind: str) -> list[str]:
        from_desc = _fields_from_description(desc)
        if from_desc:
            # Merge with entity attributes when available (entity fields first for known attrs)
            if ent_name and ent_name in entity_fields:
                ent_attrs = [str(f).lower() for f in (entity_fields.get(ent_name) or [])]
                skip = {"id", "user_id", "banned", "paid", "active", "enabled", "passed", "verified", "locked"}
                ordered: list[str] = []
                seen: set[str] = set()
                # Description order is authoritative (user intent)
                for f in from_desc:
                    if f.lower() not in skip and f not in seen:
                        ordered.append(f)
                        seen.add(f)
                # Then remaining entity attrs that look like user inputs
                for f in ent_attrs:
                    if f not in skip and f not in seen and f not in {"status"}:
                        # only add if related soft match to description or short list
                        ordered.append(f)
                        seen.add(f)
                return ordered[:8]
            return from_desc[:8]

        if not ent_name or ent_name not in entity_fields:
            return []
        fields = [str(f) for f in (entity_fields.get(ent_name) or [])]
        skip = {
            "id", "user_id", "banned", "paid", "active", "enabled",
            "passed", "verified", "locked", "status",
        }
        prefer = ["name", "patient_name", "phone", "address", "email", "title", "date", "time", "slot", "city", "notes", "description", "quantity", "price"]
        ordered = [f for f in prefer if f in fields or f.lower() in {x.lower() for x in fields}]
        # normalize case to actual field names
        lower_map = {x.lower(): x for x in fields}
        ordered = [lower_map.get(f.lower(), f) for f in ordered]
        for f in fields:
            if f.lower() not in skip and f not in ordered and f.lower() not in {x.lower() for x in ordered}:
                ordered.append(f)
        return ordered[:8]


    for cmd in program.commands:
        cn = cmd.name
        desc = getattr(cmd, "description", "") or ""
        kind = _cmd_kind(cn, desc)
        if kind in ("skip", "action", "list", "mine"):
            # list/mine handled by transpiler handlers without multi-step wizard
            continue
        ent_name = _entity_for_command(cn, desc)
        caps = [k for k in entity_fields if k and k[0].isupper()]
        if not ent_name and len(caps) == 1:
            ent_name = caps[0]
        if kind == "lookup" and not ent_name and caps:
            # Prefer entity whose name appears in the command; else first contract entity
            for cand in caps:
                if cand.lower() in cn or any(p and p in cand.lower() for p in cn.split("_")):
                    ent_name = cand
                    break
            if not ent_name:
                ent_name = caps[0]
        fields = _pick_wizard_fields(ent_name, desc, kind)
        if not fields and kind == "collect":
            # Only fields evidenced in command description or entity attrs — never invent "name"
            fields = _fields_from_description(desc)
            if not fields and ent_name:
                fields = _pick_wizard_fields(ent_name, desc, kind)
        if not fields and kind == "lookup":
            fields = ["id"]
        # Structural: *scan* / *security* commands need a target input
        if not fields and any(s in cn for s in ("scan", "security", "inspect", "audit")):
            if "domain" in cn or "dns" in cn or "email" in cn:
                fields = ["domain"]
            elif "web" in cn or "site" in cn or "url" in cn:
                fields = ["url"]
            else:
                fields = ["target"]
            kind = "collect"
        if not fields and "report" in cn:
            fields = ["project"]
            kind = "collect"
        if not fields:
            continue
        steps = [{"key": f, "prompt": _prompt_for(f)} for f in fields]
        wizards.append({
            "id": cmd.name,
            "command": cmd.name,
            "entity": ent_name or "record",
            "kind": kind,
            "steps": steps,
        })

    # Wizards from DSL operations (kind=wizard)
    existing_ids = {str(w.get("id") or w.get("command")) for w in wizards}
    for op in program.operations:
        if getattr(op, "kind", None) != "wizard":
            continue
        wid = op.name or (op.meta or {}).get("command") or "flow"
        if wid in existing_ids:
            continue
        meta = op.meta or {}
        steps = list(meta.get("steps") or [])
        if not steps and op.inputs:
            steps = [{"key": k, "prompt": f"أرسل {k}"} for k in op.inputs]
        # Drop garbage keys from weak model output
        steps = [s for s in steps if isinstance(s, dict) and str(s.get("key") or "") not in ("n_x", "x", "field", "value")]
        if not steps:
            continue
        wizards.append({
            "id": wid,
            "command": meta.get("command") or wid,
            "entity": meta.get("entity") or (op.outputs[0] if op.outputs else "record"),
            "kind": meta.get("kind") or "collect",
            "steps": steps,
            "prefill_from_button": meta.get("prefill_from_button") or "",
        })
        existing_ids.add(wid)


    # Entity-driven wizards: add_X / create_X / new_X collect all entity fields (from THIS spec only)
    for cmd in result.commands:
        cn = cmd.name
        if cn in existing_ids:
            continue
        desc = (getattr(cmd, "description", None) or "") + " " + cn
        ent_name = _entity_for_command(cn, desc)
        if not ent_name:
            # add_book → Book
            for ename, fields in entity_fields.items():
                stem = ename.lower()
                if stem in cn.replace("_", "") or cn.endswith("_" + stem) or cn.startswith(stem):
                    ent_name = ename
                    break
                if cn.startswith("add_") or cn.startswith("create_") or cn.startswith("new_"):
                    tail = cn.split("_", 1)[-1]
                    if tail and (tail in stem or stem.startswith(tail) or tail.startswith(stem[:4])):
                        ent_name = ename
                        break
        if not ent_name:
            continue
        fields = entity_fields.get(ent_name) or entity_fields.get(ent_name.lower()) or []
        fields = [f for f in fields if str(f).lower() not in {"id", "user_id"}]
        if not fields:
            continue
        if cn.startswith("list_") or cn.startswith("my_") or cn in ("list", "mine"):
            continue  # list handlers, not multi-step
        steps = [{"key": f, "prompt": _prompt_for(str(f))} for f in fields[:8]]
        wizards.append({
            "id": cn,
            "command": cn,
            "entity": ent_name,
            "kind": "collect",
            "steps": steps,
        })
        existing_ids.add(cn)

    # No catalog→order template. Flows/commands only from user text / DSL.

    # Clean weak steps
    cleaned_w = []
    for w in wizards:
        st = [s for s in (w.get('steps') or []) if str(s.get('key') or '') not in ('n_x','x','field')]
        if st:
            w = dict(w, steps=st)
            cleaned_w.append(w)
        elif w.get('kind') == 'collect':
            continue
        else:
            cleaned_w.append(w)
    result.wizards = cleaned_w
    wizards = cleaned_w

    # Tools ONLY from this request's commands (and wizard input keys). Nothing saved.
    dyn: list[dict] = []
    seen_t: set[str] = set()
    for c in result.commands:
        name = (getattr(c, "name", "") or "").strip().lower()
        if not name or name in ("start", "help") or name in seen_t:
            continue
        seen_t.add(name)
        inp = "value"
        for w in wizards:
            wid = str(w.get("id") or w.get("command") or "").lower()
            if wid == name:
                steps = w.get("steps") or []
                if steps and isinstance(steps[0], dict) and steps[0].get("key"):
                    inp = str(steps[0]["key"])
                break
        dyn.append({
            "id": name,
            "title": (getattr(c, "description", None) or name),
            "input": inp,
            "source": "command",
        })
    result.defensive_tools = []
    result.dynamic_tools = dyn[:32]

    return result
