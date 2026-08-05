"""
Extract Custom DSL from user text with maximum literal fidelity.
Every clause can become a rule/operation; synonyms only expand matching, never replace user wording in effects.
No domain packs.
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from .ast import (
    ActionNode,
    ButtonNode,
    CommandNode,
    ConditionExpr,
    DSLProgram,
    EffectExpr,
    EntityNode,
    OperationNode,
    RelationNode,
    RequiresNode,
    RuleNode,
)

_GHOST = {
    "start", "help", "bot", "telegram", "user_text", "validateavailability",
    "validate", "availability", "educore", "edubot", "main", "item", "default",
    "true", "false", "none", "null", "http", "https",
}

_ADMIN_CMDS = {"admin", "ban", "mute", "broadcast", "stats", "panel"}

# Matching aids only — effects always keep user wording
_SYN_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("paid_success", (
        "دفع بنجاح", "تم الدفع", "الدفع نجح", "payment success", "paid successfully",
        "paid", "payment ok", "تم السداد", "سداد ناجح", "لو paid",
    )),
    ("success", ("بنجاح", "نجح", "تم بنجاح", "successfully", "success")),
    ("create_record", ("يسجل", "تسجيل", "يحفظ", "حفظ", "ينشئ", "إنشاء", "create", "save", "store", "record")),
    ("reply_show", ("يعرض", "يرسل", "يؤكد", "رد", "reply", "show", "send", "confirm", "يطلب")),
    ("enable", ("يتيح", "يفتح", "تمكين", "enable", "unlock", "allow", "activate")),
    ("compute_score", (
        "يحسب الدرجة", "حساب الدرجة", "احسب الدرجة", "compute score", "calculate score",
        "يحسب النقاط", "مجموع الدرجات", "كل إجابة", "كل صح",
    )),
    ("compute_total", ("يحسب المجموع", "حساب المجموع", "compute total", "calculate total", "المجموع")),
    ("threshold", ("بنسبة", "أكثر من", "أكبر من", "على الأقل", "at least", "greater than", "more than", "لا يقل عن", ">=")),
    ("threshold_lt", ("أقل من", "أقل من أو يساوي", "less than", "at most", "<=")),
    ("choice", ("اختار", "اختيار", "يختار", "choose", "select", "picked")),
    ("validate", ("التحقق", "يتحقق", "validate", "check", "تأكد")),
]


def _norm_text(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي")
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def _contains_any(text: str, phrases: tuple[str, ...]) -> str | None:
    nt = _norm_text(text)
    best, best_len = None, 0
    for p in phrases:
        np = _norm_text(p)
        if np and np in nt and len(np) > best_len:
            best, best_len = p, len(np)
    return best


def _signal(text: str, group: str) -> bool:
    for name, phrases in _SYN_GROUPS:
        if name == group:
            return _contains_any(text, phrases) is not None
    return False


def _similarity(a: str, b: str) -> float:
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return 0.0
    if na == nb or na in nb or nb in na:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _best_button_match(label: str, buttons: list[ButtonNode], min_score: float = 0.5) -> ButtonNode | None:
    if not label or not buttons:
        return None
    best, best_sc = None, 0.0
    for b in buttons:
        sc = max(_similarity(label, b.label), _similarity(label, b.callback_id.replace("_", " ")))
        if sc > best_sc:
            best_sc, best = sc, b
    return best if best_sc >= min_score else None


def _best_entity_match(text: str, entities: list[EntityNode]) -> str | None:
    if not text or not entities:
        return None
    best, best_sc = None, 0.0
    for e in entities:
        sc = _similarity(text, e.name)
        if e.name.lower() in _norm_text(text):
            sc = max(sc, 0.95)
        if sc > best_sc:
            best_sc, best = sc, e.name
    return best if best_sc >= 0.5 else None


def _ascii_ident(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (s or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or not re.match(r"[A-Za-z]", s[0]):
        s = "n_" + (s or "x")
    return s[:48]


def _infer_type(attr: str) -> str:
    a = (attr or "").lower()
    if a == "user_id":
        return "int"
    if a in ("price", "amount", "score", "qty", "quantity", "stock", "duration",
             "duration_min", "duration_weeks", "level", "count", "total", "percent",
             "ratio", "progress", "weight", "points"):
        return "int"
    if a in ("paid", "active", "enabled", "done", "completed", "is_admin"):
        return "bool"
    return "str"


def _parse_number(s: str) -> str | None:
    m = re.search(r"(\d+(?:\.\d+)?)", s or "")
    return m.group(1) if m else None


# ── surface: entities / commands / buttons ────────────────────────────────

def _entities_from_text(text: str) -> list[EntityNode]:
    found: list[EntityNode] = []
    seen: set[str] = set()

    def add(name: str, attrs: list[str] | None = None) -> None:
        n = _ascii_ident(name)
        key = n.lower()
        if not n or key in seen or key in _GHOST or len(n) < 2:
            return
        if key.startswith(("validate", "manage", "create", "update", "delete")):
            return
        seen.add(key)
        attrs = [a for a in (attrs or []) if a and a not in _GHOST]
        found.append(EntityNode(name=n[:1].upper() + n[1:], attributes=attrs, attr_types={a: _infer_type(a) for a in attrs}))

    for m in re.finditer(
        r"(?:كيان|نموذج|جدول|entity|model|table)\s+[«\"']?([A-Za-z][A-Za-z0-9_]{1,40})[»\"']?"
        r"(?:\s+(?:يحتاج|يتطلب|requires|needs)\s+([^\n.]{3,120}))?",
        text,
        re.I,
    ):
        attrs = []
        if m.group(2):
            attrs = [_ascii_ident(p).lower() for p in re.split(r"[,، و&/]+", m.group(2)) if _ascii_ident(p)]
        add(m.group(1), attrs)
    return found


def _commands_from_text(text: str) -> list[CommandNode]:
    found: list[CommandNode] = []
    seen: set[str] = set()

    def add(cmd: str, desc: str = "") -> None:
        cmd = re.sub(r"[^a-z0-9_]", "", (cmd or "").lower().lstrip("/"))
        if not cmd or len(cmd) < 2 or cmd in seen or cmd in ("http", "https", "www", "telegram", "python"):
            return
        seen.add(cmd)
        admin = cmd in _ADMIN_CMDS or any(k in (desc or "").lower() for k in ("أدمن", "admin", "مشرف", "إدارة"))
        found.append(CommandNode(name=cmd, description=(desc or cmd)[:100], admin_only=admin))

    for m in re.finditer(r"/(?P<cmd>[a-zA-Z][a-zA-Z0-9_]{1,32})\b\s*[-–—:：]?\s*(?P<desc>[^\n/]{0,80})", text):
        add(m.group("cmd"), m.group("desc").strip())
    if "start" not in seen:
        found.insert(0, CommandNode(name="start", description="تشغيل البوت"))
        seen.add("start")
    if "help" not in seen:
        found.append(CommandNode(name="help", description="المساعدة"))
    return found


def _buttons_from_text(text: str) -> list[ButtonNode]:
    buttons: list[ButtonNode] = []
    seen: set[str] = set()

    def add(label: str) -> None:
        label = re.sub(r"\s+", " ", (label or "").strip())
        label = re.sub(r"[.،,;:]+$", "", label).strip()
        if not label or label in seen or not (2 <= len(label) <= 48):
            return
        if any(x in label for x in ("يجب", "أنشئ", "http", "يقوم")):
            return
        seen.add(label)
        cb = re.sub(r"[^\w]+", "_", label, flags=re.UNICODE).strip("_").lower()[:40] or f"btn_{len(buttons)}"
        cb_ascii = re.sub(r"[^a-zA-Z0-9_]", "_", cb)
        cb_ascii = re.sub(r"_+", "_", cb_ascii).strip("_") or f"btn_{len(buttons)}"
        buttons.append(ButtonNode(label=label, callback_id=cb_ascii[:40]))

    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        s = line.strip().lower()
        if any(k in s for k in ("الأزرار", "ازرار", "buttons", "القائمة", "menu")) and len(s) < 40:
            start = i + 1
            break
    if start is not None:
        for line in lines[start:]:
            s = line.strip()
            if not s:
                continue
            if len(s) < 30 and any(k in s for k in ("الأوامر", "الكيانات", "طريقة", "commands", "features", "المتطلبات")):
                break
            m = re.match(r"^[\s\-•*]+(.+)$", s)
            if m:
                add(m.group(1).strip())
            elif 2 <= len(s) <= 40 and "/" not in s and not s.endswith(":"):
                add(s)
    for m in re.finditer(r"(?:زر|button)\s*[:=]?\s*[«\"'\[]([^»\"'\]]{2,40})[»\"'\]]", text, re.I):
        add(m.group(1).strip())
    return buttons[:24]


def _relations_from_text(text: str, entities: list[EntityNode]) -> list[RelationNode]:
    relations: list[RelationNode] = []
    ent_map = {e.name.lower(): e for e in entities}
    for m in re.finditer(
        r"([A-Za-z][A-Za-z0-9_]{1,30})\s+(?:يحتاج|يتطلب|requires|needs)\s+([^\n.]{3,100})",
        text, re.I,
    ):
        ename = _ascii_ident(m.group(1))
        ops = [_ascii_ident(p).lower() for p in re.split(r"[,، و&]+", m.group(2)) if _ascii_ident(p)]
        ops = [o for o in ops if o and o not in _GHOST]
        ent = ent_map.get(ename.lower()) or EntityNode(name=ename[:1].upper() + ename[1:], attributes=ops)
        relations.append(RelationNode(entity=ent, requires=RequiresNode(operands=ops), action=ActionNode(name=f"Manage{ent.name}"), raw=m.group(0)[:120]))
    for m in re.finditer(r"(?:يتحقق من|التحقق من|validate|check)\s+([A-Za-z][A-Za-z0-9_]{1,40})", text, re.I):
        target = _ascii_ident(m.group(1))
        relations.append(RelationNode(entity=None, requires=None, action=ActionNode(name=f"Validate{target[:1].upper() + target[1:]}"), raw=m.group(0)[:120]))
    covered = {(r.entity.name.lower() if r.entity else "") for r in relations}
    for e in entities:
        if e.name.lower() not in covered:
            relations.append(RelationNode(entity=e, requires=RequiresNode(operands=list(e.attributes) or ["id"]), action=ActionNode(name=f"Manage{e.name}"), raw=f"Entity({e.name})"))
    return relations


def _operations_from_text(text: str, buttons: list[ButtonNode]) -> list[OperationNode]:
    ops: list[OperationNode] = []
    t = text.lower()
    if any(k in text or k in t for k in ("تكرار", "لكل", "for each", "loop", "عدة مرات", "قائمة من", "واحداً تلو")):
        ops.append(OperationNode(kind="loop", name="IterateItems", inputs=["items"], outputs=["item"], meta={"signal": "repetition"}))
    if any(k in text or k in t for k in ("إذا", "لو", "if ", "else", "اختيار", "اختار")):
        branches = [{"label": b.label, "target": b.callback_id} for b in buttons] if buttons else [
            {"label": "branch_a", "target": "path_a"}, {"label": "branch_b", "target": "path_b"},
        ]
        ops.append(OperationNode(kind="decision", name="BranchOnChoice", inputs=["choice"], outputs=["branch"], meta={"signal": "decision", "branches": branches}))
    if any(k in text or k in t for k in ("يحفظ", "تخزين", "قاعدة بيانات", "store", "save", "database", "يسجل")):
        ops.append(OperationNode(kind="store", name="PersistEntity", inputs=["entity", "fields"], outputs=["id"], meta={"signal": "storage"}))
    if any(k in text or k in t for k in ("أمر", "أوامر", "/start", "زر", "أزرار", "command", "button")):
        ops.append(OperationNode(kind="receive", name="ReceiveInput", inputs=["update"], outputs=["payload"], meta={"signal": "input"}))
    if any(k in text or k in t for k in ("يرسل", "يعرض", "رد", "reply", "send", "message")):
        ops.append(OperationNode(kind="emit", name="EmitReply", inputs=["text"], outputs=[], meta={"signal": "output"}))
    for i, m in enumerate(re.finditer(r"(?:^|\n)\s*(?:\d+|[\u0660-\u0669]+)[\.\)\-\:]\s*([^\n]{5,160})", text)):
        label = m.group(1).strip()
        ops.append(OperationNode(kind="compute", name=f"step_{i+1}", inputs=["context"], outputs=["context"], body_refs=[label], meta={"ordinal": i + 1, "label": label[:160]}))
    return ops


# ── literal clause split ──────────────────────────────────────────────────

def _split_clauses(text: str) -> list[str]:
    """Split user text into literal clauses without dropping content."""
    clauses: list[str] = []
    # numbered items first
    for m in re.finditer(r"(?:^|\n)\s*(?:\d+|[\u0660-\u0669]+)[\.\)\-\:]\s*([^\n]{3,200})", text):
        clauses.append(m.group(1).strip())
    # bullet lines
    for m in re.finditer(r"(?:^|\n)\s*[\-•*]\s*([^\n]{3,200})", text):
        c = m.group(1).strip()
        if c not in clauses:
            clauses.append(c)
    # إذا/لو sentences
    for m in re.finditer(r"((?:إذا|لو|if)\s+[^\n.]{5,200})", text, re.I):
        c = m.group(1).strip()
        if c not in clauses:
            clauses.append(c)
    # قبل …
    for m in re.finditer(r"((?:قبل|before)\s+[^\n.]{5,160})", text, re.I):
        c = m.group(1).strip()
        if c not in clauses:
            clauses.append(c)
    # compute sentences
    for m in re.finditer(r"((?:يحسب|احسب|حساب|compute|calculate)[^\n.]{3,120})", text, re.I):
        c = m.group(1).strip()
        if c not in clauses:
            clauses.append(c)
    # threshold fragments — skip if clearly a mid-sentence residue (has ثم/then after number)
    for m in re.finditer(r"((?:بنسبة|أكثر من|أكبر من|أقل من)[^\n.]{2,100})", text, re.I):
        c = m.group(1).strip()
        if re.search(r"\d\s*%?\s*(?:ثم|بعدها|then)\b", c, re.I):
            continue
        if c not in clauses:
            clauses.append(c)
    return clauses


# ── conditions / effects (literal-preserving) ─────────────────────────────

def _split_bool(expr: str) -> tuple[list[str], str]:
    """Split on و/أو/and/or. Returns (parts, mode) mode=all|any."""
    if re.search(r"\s+أو\s+|\s+or\s+", expr, re.I):
        parts = re.split(r"\s+أو\s+|\s+or\s+", expr, flags=re.I)
        parts = [p.strip() for p in parts if p.strip()]
        if 1 < len(parts) <= 4:
            return parts, "any"
    if re.search(r"\s+و\s+|\s+and\s+", expr, re.I):
        parts = re.split(r"\s+و\s+|\s+and\s+", expr, flags=re.I)
        parts = [p.strip() for p in parts if p.strip()]
        # avoid splitting Arabic idafa noise: only if parts look like conditions
        if 1 < len(parts) <= 4 and all(len(p) >= 2 for p in parts):
            return parts, "all"
    return [expr.strip()], "all"


def _atomic_condition(part: str, buttons: list[ButtonNode]) -> ConditionExpr:
    part = part.strip()
    cm = re.search(r"(?:اختار|اختيار|يختار|choose|select)\s+(.+)", part, re.I)
    if cm or _signal(part, "choice"):
        choice = cm.group(1).strip() if cm else re.sub(r".*?(?:اختار|اختيار|choose|select)\s+", "", part, flags=re.I).strip()
        # strip trailing effect words from choice fragment
        choice = re.split(r"\s+(?:ثم|بعدها|then)\s+", choice, maxsplit=1)[0].strip()
        btn = _best_button_match(choice, buttons)
        if btn:
            return ConditionExpr(left="choice", op="eq", right=btn.callback_id, raw=f"{part}|label={btn.label}")
        return ConditionExpr(left="choice", op="eq", right=choice[:60], raw=part)

    if _signal(part, "paid_success") or (
        _signal(part, "success") and any(k in _norm_text(part) for k in ("دفع", "pay", "paid", "سداد"))
    ):
        return ConditionExpr(left="paid", op="truthy", right="true", raw=part)

    if _signal(part, "success"):
        return ConditionExpr(left="success", op="truthy", right="true", raw=part)

    # field comparisons FIRST (amount أكبر من 0) before generic threshold
    m = re.search(r"([A-Za-z_][A-Za-z0-9_]{1,30})\s*(?:==|=|equals)\s*([^\s،,]{1,40})", part)
    if m:
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="eq", right=m.group(2).strip(), raw=part)
    m = re.search(r"([A-Za-z_][A-Za-z0-9_]{1,30})\s*(?:>=|أكبر من أو يساوي|لا يقل عن)\s*(\d+(?:\.\d+)?)", part)
    if m:
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="gte", right=m.group(2), raw=part)
    m = re.search(r"([A-Za-z_][A-Za-z0-9_]{1,30})\s*(?:>|أكبر من|أكثر من)\s*(\d+(?:\.\d+)?)", part)
    if m:
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="gt", right=m.group(2), raw=part)
    m = re.search(r"([A-Za-z_][A-Za-z0-9_]{1,30})\s*(?:<|أقل من)\s*(\d+(?:\.\d+)?)", part)
    if m:
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="lt", right=m.group(2), raw=part)

    num = _parse_number(part)
    if num and (_signal(part, "threshold") or _signal(part, "threshold_lt") or "%" in part or "نسبة" in part):
        op = "lte" if _signal(part, "threshold_lt") or "أقل" in part else "gte"
        left = "score" if any(k in part for k in ("درجة", "score", "نقاط")) else "progress"
        return ConditionExpr(left=left, op=op, right=num, raw=part)

    return ConditionExpr(left="signal", op="contains", right=part[:60], raw=part)


def _conditions_from_clause(cond_raw: str, buttons: list[ButtonNode]) -> tuple[list[ConditionExpr], str]:
    parts, mode = _split_bool(cond_raw)
    # propagate choice/select prefix across OR/AND fragments
    prefix = ""
    m = re.match(r"((?:اختار|اختيار|يختار|choose|select)\s+)", cond_raw, re.I)
    if m:
        prefix = m.group(1)
    fixed: list[str] = []
    for i, p in enumerate(parts):
        if i > 0 and prefix and not re.search(r"(?:اختار|اختيار|choose|select)", p, re.I):
            # fragment like "التسجيل" after "اختار الدورات أو"
            fixed.append(prefix + p)
        else:
            fixed.append(p)
    return [_atomic_condition(p, buttons) for p in fixed], mode


def _effects_from_clause(eff_raw: str, entities: list[EntityNode]) -> list[EffectExpr]:
    """Effects keep the user's literal wording in value/raw."""
    effects: list[EffectExpr] = []
    literal = eff_raw.strip()

    if _signal(eff_raw, "create_record"):
        target = _best_entity_match(eff_raw, entities) or "record"
        for en in ("Enrollment", "Order", "Payment", "Certificate", "ExamAttempt", "Homework", "Student", "Course"):
            if en.lower() in _norm_text(eff_raw) or en in eff_raw:
                target = en
                break
        effects.append(EffectExpr(kind="create", target=target, value=literal[:80], raw=literal))

    if _signal(eff_raw, "enable"):
        tgt = "certificate" if any(k in _norm_text(eff_raw) for k in ("شهاده", "certificate")) else literal[:40]
        effects.append(EffectExpr(kind="enable", target=tgt, value=literal[:80], raw=literal))

    if _signal(eff_raw, "validate"):
        vm = re.search(r"(Validate[A-Za-z0-9_]{2,40})", eff_raw)
        effects.append(EffectExpr(kind="call", target=vm.group(1) if vm else "ValidateAvailability", value=literal[:80], raw=literal))

    # always keep a reply with the exact user phrase for observability
    if _signal(eff_raw, "reply_show") or not effects:
        effects.append(EffectExpr(kind="reply", target="message", value=literal[:120], raw=literal))

    seen: set[tuple[str, str]] = set()
    uniq: list[EffectExpr] = []
    for e in effects:
        key = (e.kind, e.target)
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return uniq


def _rule_fingerprint(rule: RuleNode) -> str:
    conds = tuple(sorted((c.left, c.op, str(c.right)) for c in rule.conditions))
    effs = tuple(sorted((e.kind, e.target) for e in rule.effects))
    return f"{rule.kind}|{conds}|{effs}"


def _merge_rules(rules: list[RuleNode]) -> list[RuleNode]:
    by_key: dict[str, RuleNode] = {}
    order: list[str] = []
    for r in rules:
        fp = _rule_fingerprint(r)
        soft = None
        if r.kind in ("threshold", "conditional") and r.conditions:
            c0 = r.conditions[0]
            if c0.left in ("progress", "score") and c0.op in ("gte", "gt", "lte", "lt"):
                soft = f"thr|{c0.left}|{c0.op}|{c0.right}"
        key = soft or fp
        if key in by_key:
            existing = by_key[key]
            seen = {(e.kind, e.target) for e in existing.effects}
            for e in r.effects:
                if (e.kind, e.target) not in seen:
                    existing.effects.append(e)
                    seen.add((e.kind, e.target))
            if len(r.raw) > len(existing.raw):
                existing.raw = r.raw
            if len(r.conditions) > len(existing.conditions):
                existing.conditions = list(r.conditions)
            if existing.kind == "threshold" and r.kind == "conditional":
                existing.kind = "conditional"
                existing.name = r.name
        else:
            by_key[key] = RuleNode(name=r.name, kind=r.kind, conditions=list(r.conditions), effects=list(r.effects), raw=r.raw)
            order.append(key)
    return [by_key[k] for k in order]


def _parse_compute(clause: str) -> RuleNode | None:
    """Literal compute patterns: sum answers, +N per correct, score from N."""
    if not re.search(r"يحسب|احسب|حساب|compute|calculate|مجموع|كل صح|كل إجابة", clause, re.I):
        return None
    # كل إجابة صح +N / كل صح نقطة
    m = re.search(r"كل\s+(?:إجابة\s+)?(?:صح|صحيح)?\s*[+\-]?(\d+)", clause)
    if m:
        weight = m.group(1)
        return RuleNode(
            name="compute_weighted",
            kind="compute",
            conditions=[],
            effects=[
                EffectExpr(kind="accumulate", target="score", value=f"answers*{weight}", raw=clause),
                EffectExpr(kind="set", target="score", value="computed", raw=clause),
                EffectExpr(kind="reply", target="message", value=clause[:120], raw=clause),
            ],
            raw=clause[:160],
        )
    target = "total" if any(k in clause for k in ("مجموع", "total")) else "score"
    return RuleNode(
        name="compute_score",
        kind="compute",
        conditions=[],
        effects=[
            EffectExpr(kind="accumulate", target=target, value="answers", raw=clause),
            EffectExpr(kind="set", target=target, value="computed", raw=clause),
            EffectExpr(kind="reply", target="message", value=clause[:120], raw=clause),
        ],
        raw=clause[:160],
    )


def _rules_from_text(text: str, entities: list[EntityNode], buttons: list[ButtonNode]) -> list[RuleNode]:
    rules: list[RuleNode] = []
    idx = 0

    def rid(prefix: str) -> str:
        nonlocal idx
        idx += 1
        return f"{prefix}_{idx}"

    clauses = _split_clauses(text)

    for clause in clauses:
        # conditional: إذا/لو … ثم …
        m = re.search(
            r"(?:إذا|لو|if)\s+(?P<cond>.+?)\s+(?:ثم|بعدها|بعد ذلك|then)\s+(?P<eff>.+)$",
            clause,
            re.I,
        )
        if m:
            cond_raw = m.group("cond").strip()
            eff_raw = m.group("eff").strip()
            conditions, mode = _conditions_from_clause(cond_raw, buttons)
            effects = _effects_from_clause(eff_raw, entities)
            # encode composite mode on first condition raw tag
            if mode == "any" and conditions:
                conditions[0].raw = f"ANY|{conditions[0].raw}"
            rules.append(RuleNode(name=rid("rule"), kind="conditional", conditions=conditions, effects=effects, raw=clause[:160]))
            continue

        # threshold standalone — only if clause opens with threshold cue (not mid-conditional residue)
        if re.match(r"^(?:ثم|بعدها|after)\b", clause, re.I):
            continue
        m = re.search(
            r"^(?:بنسبة|أكثر من|أكبر من|أقل من|at least|greater than|less than)\s*(\d+(?:\.\d+)?)\s*%?(.+)?$",
            clause,
            re.I,
        )
        if m:
            num = m.group(1)
            rest = (m.group(2) or "").strip()
            op = "lte" if any(k in clause for k in ("أقل", "less")) else "gte"
            left = "score" if any(k in clause for k in ("درجة", "score")) else "progress"
            effects = _effects_from_clause(rest, entities) if rest else [
                EffectExpr(kind="reply", target="message", value=clause[:120], raw=clause)
            ]
            rules.append(RuleNode(
                name=rid("threshold"), kind="threshold",
                conditions=[ConditionExpr(left=left, op=op, right=num, raw=clause[:80])],
                effects=effects, raw=clause[:160],
            ))
            continue

        # compute
        cr = _parse_compute(clause)
        if cr:
            cr.name = rid("compute")
            rules.append(cr)
            continue

        # before-guard
        m = re.search(
            r"(?:قبل|before)\s+(?P<before>.+?)\s+(?:يتم|يجب)?\s*(?P<act>(?:التحقق|يتحقق|validate|check).+|Validate[A-Za-z0-9_]+)$",
            clause,
            re.I,
        )
        if m:
            before = m.group("before").strip()[:40]
            act = m.group("act").strip()
            vm = re.search(r"(Validate[A-Za-z0-9_]{2,40})", act)
            target = vm.group(1) if vm else "ValidateAvailability"
            rules.append(RuleNode(
                name=rid("guard"), kind="conditional",
                conditions=[ConditionExpr(left="before", op="eq", right=before, raw=before)],
                effects=[
                    EffectExpr(kind="call", target=target, value=clause[:80], raw=act),
                    EffectExpr(kind="reply", target="message", value=clause[:120], raw=clause),
                ],
                raw=clause[:160],
            ))
            continue

        # bare choice without explicit إذا
        m = re.search(
            r"(?:اختار|اختيار|يختار)\s+(?P<label>[^،.]{2,50})\s*(?:ثم|بعدها|→|->)?\s*(?P<eff>.*)$",
            clause,
            re.I,
        )
        if m:
            label = m.group("label").strip()
            eff_raw = (m.group("eff") or "").strip()
            if any(_similarity(label, c.right) > 0.8 or (f"label=" in (c.raw or "") and _similarity(label, c.raw) > 0.5)
                   for r in rules for c in r.conditions if c.left == "choice"):
                continue
            btn = _best_button_match(label, buttons)
            right = btn.callback_id if btn else label
            effects = _effects_from_clause(eff_raw, entities) if eff_raw else [
                EffectExpr(kind="goto", target=(btn.callback_id if btn else _ascii_ident(label)), value=label, raw=clause),
                EffectExpr(kind="reply", target="message", value=clause[:120], raw=clause),
            ]
            rules.append(RuleNode(
                name=rid("choice"), kind="conditional",
                conditions=[ConditionExpr(left="choice", op="eq", right=right, raw=f"{label}|label={(btn.label if btn else label)}")],
                effects=effects, raw=clause[:160],
            ))

    return _merge_rules(rules)


def extract_dsl(text: str) -> DSLProgram:
    full = (text or "").strip()
    if len(full) > 200_000:
        full = full[:200_000]
    entities = _entities_from_text(full)
    commands = _commands_from_text(full)
    buttons = _buttons_from_text(full)
    relations = _relations_from_text(full, entities)
    operations = _operations_from_text(full, buttons)
    rules = _rules_from_text(full, entities, buttons)
    t = full.lower()
    wants_db = any(k in full or k in t for k in ("قاعدة بيانات", "database", "يحفظ", "تخزين", "sqlite", "postgres"))
    wants_files = any(k in full or k in t for k in ("صورة", "ملف", "رفع", "photo", "file", "upload", "document"))
    h = hashlib.sha256(full.encode("utf-8")).hexdigest()[:16]
    return DSLProgram(
        relations=relations,
        operations=operations,
        entities=entities,
        commands=commands,
        buttons=buttons,
        rules=rules,
        source_hash=h,
        wants_database=wants_db,
        wants_files=wants_files,
    )
