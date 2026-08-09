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
from ..ontology.telegram_capabilities import (
    any_admin_typical,
    commands_from_capability_evidence,
    resolve_capabilities,
)

_GHOST = {
    "start", "help", "bot", "telegram", "user_text", "validateavailability",
    "validate", "availability", "educore", "edubot", "main", "item", "default",
    "true", "false", "none", "null", "http", "https",
}

_ADMIN_CMDS = {"admin", "ban", "mute", "kick", "unban", "unmute", "promote", "broadcast", "stats", "panel"}

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
    if a in ("paid", "active", "enabled", "done", "completed", "is_admin", "banned",
             "passed", "verified", "locked"):
        return "bool"
    return "str"


def _parse_number(s: str) -> str | None:
    m = re.search(r"(\d+(?:\.\d+)?)", s or "")
    return m.group(1) if m else None


# ── section helpers (explicit structured specs) ───────────────────────────

_SECTION_STOP = (
    "الأوامر", "الاوامر", "commands",
    "الأزرار", "الازرار", "ازرار", "buttons", "القائمة الرئيسية", "القائمة",
    "القواعد", "قواعد", "rules", "الشروط",
    "الكيانات", "كيانات", "entities", "النماذج", "نماذج البيانات", "data models",
    "التدفقات", "تدفقات", "flows", "wizards",
    "الخدمات", "خدمات", "services",
    "الميزات", "ميزات", "features",
    "المتطلبات", "طريقة", "الإطار", "قاعدة البيانات", "database",
    "roles", "الأدوار",
)


def _section_lines(text: str, *titles: str) -> list[str]:
    """Return body lines under the first matching section header until next section."""
    lines = (text or "").splitlines()
    start = None
    titles_l = [t.lower() for t in titles]
    for i, line in enumerate(lines):
        s = line.strip().lower().rstrip(":：")
        if len(s) > 60:
            continue
        if any(t in s for t in titles_l):
            start = i + 1
            break
    if start is None:
        return []
    out: list[str] = []
    for line in lines[start:]:
        raw = line.strip()
        if not raw:
            if out:
                continue
            continue
        low = raw.lower().rstrip(":：")
        # next section header
        if len(raw) < 50 and any(k in low for k in _SECTION_STOP):
            # allow continuing if this line is still content under same section style
            if not any(t in low for t in titles_l):
                break
        out.append(raw)
    return out


def _strip_bullet(s: str) -> str:
    return re.sub(r"^[\s\-•*️⃣\d\.\)\(]+", "", (s or "").strip()).strip()


def _looks_like_rule(s: str) -> bool:
    t = (s or "").strip()
    if re.match(r"^(?:لو|إذا|اذا|if)\b", t, re.I):
        return True
    if re.search(r"(?:ثم|بعدها|then)\b", t, re.I) and re.search(r"(?:لو|إذا|اذا|if)\b", t, re.I):
        return True
    return False


def _parse_attrs(raw: str) -> list[str]:
    attrs: list[str] = []
    for p in re.split(r"[,،/;|&]+", raw or ""):
        a = _ascii_ident(p).lower()
        if a and a not in _GHOST and len(a) >= 1:
            attrs.append(a)
    return attrs


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
        found.append(
            EntityNode(
                name=n[:1].upper() + n[1:],
                attributes=attrs,
                attr_types={a: _infer_type(a) for a in attrs},
            )
        )

    # 1) Explicit section: الكيانات / entities / نماذج
    for line in _section_lines(
        text,
        "الكيانات", "كيانات", "entities", "النماذج", "نماذج البيانات",
        "data models", "models",
    ):
        body = _strip_bullet(line)
        if not body or _looks_like_rule(body):
            continue
        # Skip flow headers: register @User : title
        if "@" in body:
            continue
        # Student (id, name, email)  |  Student: id, name — require explicit fields
        m = re.match(
            r"^[«\"']?([A-Za-z][A-Za-z0-9_]{1,40})[»\"']?\s*"
            r"(?:[\(:：]\s*([^\)\n]{1,120})[\)]?)?",
            body,
        )
        if m and (m.group(2) is not None or "(" in body):
            add(m.group(1), _parse_attrs(m.group(2) or ""))
            continue
        m = re.match(
            r"^[«\"']?([A-Za-z][A-Za-z0-9_]{1,40})[»\"']?\s*[-–—:：]\s*(.+)$",
            body,
        )
        if m and m.group(2) and not m.group(2).strip().startswith("@"):
            fields_raw = m.group(2)
            if re.search(r"[ا-ي]", fields_raw) and not re.search(r"[a-zA-Z_]", fields_raw):
                continue
            add(m.group(1), _parse_attrs(fields_raw))

    # 2) Inline patterns: كيان Student يحتاج ... / entity Student (a, b)
    for m in re.finditer(
        r"(?:كيان|نموذج|جدول|entity|model|table)\s+[«\"']?([A-Za-z][A-Za-z0-9_]{1,40})[»\"']?"
        r"(?:\s*[\(:：]\s*([^\)\n]{1,120})[\)]?)?"
        r"(?:\s+(?:يحتاج|يتطلب|requires|needs)\s+([^\n.]{3,120}))?",
        text,
        re.I,
    ):
        attrs = _parse_attrs(m.group(2) or "") + _parse_attrs(m.group(3) or "")
        add(m.group(1), attrs)

    # 3) CapWord lists anywhere: Student (id, name, email)
    for m in re.finditer(
        r"\b([A-Z][A-Za-z0-9_]{1,40})\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\s*,\s*[a-zA-Z_][a-zA-Z0-9_]*){0,12})\s*\)",
        text,
    ):
        add(m.group(1), _parse_attrs(m.group(2)))

    # 4) NO free-form domain noun packs.
    # Entities come only from explicit user declarations (sections / CapWord(fields)).
    return found


def _commands_from_text(text: str) -> list[CommandNode]:
    """Extract commands with anti-hallucination rules.

    Priority:
      1) Explicit /command tokens (and optional section)
      2) Only if none: grounded freeform / stems / verbs from user words
    Never mix freeform packs on top of an explicit command list.
    """
    found: list[CommandNode] = []
    seen: set[str] = set()

    def add(cmd: str, desc: str = "") -> None:
        cmd = re.sub(r"[^a-z0-9_]", "", (cmd or "").lower().lstrip("/"))
        if not cmd or len(cmd) < 2 or cmd in seen or cmd in ("http", "https", "www", "telegram", "python"):
            return
        seen.add(cmd)
        # Capabilities from command name + description only (no domain packs)
        caps = resolve_capabilities(cmd, desc or "")
        admin = (
            cmd in _ADMIN_CMDS
            or any(k in (desc or "") for k in ("أدمن", "ادمن", "admin", "مشرف", "إدارة", "للأدمن"))
            or any_admin_typical(caps)
        )
        found.append(
            CommandNode(
                name=cmd,
                description=(desc or cmd)[:100],
                admin_only=admin,
                capabilities=caps,
            )
        )

    section = _section_lines(text, "الأوامر", "الاوامر", "commands", "الأوامر المطلوبة")
    scan_text = "\n".join(section) if section else text

    for m in re.finditer(
        r"/(?P<cmd>[a-zA-Z][a-zA-Z0-9_]{1,32})\b\s*[-–—:：]?\s*(?P<desc>[^\n/]{0,100})",
        scan_text,
    ):
        add(m.group("cmd"), m.group("desc").strip())

    if section:
        for m in re.finditer(
            r"/(?P<cmd>[a-zA-Z][a-zA-Z0-9_]{1,32})\b\s*[-–—:：]?\s*(?P<desc>[^\n/]{0,100})",
            text,
        ):
            add(m.group("cmd"), m.group("desc").strip())

    explicit = [c.name for c in found if c.name not in ("start", "help")]

    # NO freeform keyword→command packs (they hallucinate features from prose).
    # Natural language without /commands is handled by SpecTranslator upstream.
    # Formal extractor only accepts:
    #   1) explicit /command tokens (above)
    #   2) section lines: name — description  (ascii command id)
    if not explicit:
        for line in _section_lines(
            text, "الأوامر", "الاوامر", "commands", "الأوامر المطلوبة", "functions", "الوظائف"
        ) or text.splitlines():
            body = _strip_bullet(line)
            if not body or len(body) > 120 or _looks_like_rule(body):
                continue
            # /cmd already handled; here: register — تسجيل  |  register: signup
            m = re.match(
                r"^[/`']?(?P<cmd>[a-zA-Z][a-zA-Z0-9_]{1,32})[`']?\s*[-–—:：]\s*(?P<desc>.+)$",
                body,
            )
            if m:
                add(m.group("cmd"), m.group("desc").strip()[:100])
                continue
            # bare /cmd on its own line
            m = re.match(r"^/(?P<cmd>[a-zA-Z][a-zA-Z0-9_]{1,32})\s*$", body)
            if m:
                add(m.group("cmd"), m.group("cmd"))

    # Promote evidenced Telegram capabilities from prose → commands.
    # Example: "حظر وطرد وكتم" → ban / kick / mute (not a domain pack).
    for cmd_name, caps, desc in commands_from_capability_evidence(text):
        if cmd_name in seen:
            # merge capabilities into existing node
            for c in found:
                if c.name == cmd_name:
                    merged = list(dict.fromkeys(list(c.capabilities or []) + list(caps)))
                    c.capabilities = merged
                    if any_admin_typical(merged):
                        c.admin_only = True
                    break
            continue
        seen.add(cmd_name)
        found.append(
            CommandNode(
                name=cmd_name,
                description=(desc or cmd_name)[:100],
                admin_only=any_admin_typical(caps),
                capabilities=list(caps),
            )
        )

    # No free-verb domain stems. Commands only from user text.

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
        # Never treat rules / commands / entities as buttons
        if _looks_like_rule(label):
            return
        if label.startswith("/"):
            return
        if any(x in label for x in ("يجب", "أنشئ", "http", "يقوم", "يحتاج", "يتطلب")):
            return
        if re.match(r"^[A-Za-z][A-Za-z0-9_]*\s*\(", label):
            return
        seen.add(label)
        cb = re.sub(r"[^\w]+", "_", label, flags=re.UNICODE).strip("_").lower()[:40] or f"btn_{len(buttons)}"
        cb_ascii = re.sub(r"[^a-zA-Z0-9_]", "_", cb)
        cb_ascii = re.sub(r"_+", "_", cb_ascii).strip("_") or f"btn_{len(buttons)}"
        buttons.append(ButtonNode(label=label, callback_id=cb_ascii[:40] or f"btn_{len(buttons)}"))

    for line in _section_lines(
        text,
        "الأزرار", "الازرار", "ازرار", "buttons",
        "القائمة الرئيسية", "القائمة", "main menu", "menu buttons",
    ):
        body = _strip_bullet(line)
        if not body or body.endswith(":"):
            continue
        if _looks_like_rule(body):
            continue
        if len(body) < 50 and any(k in body.lower() for k in _SECTION_STOP):
            continue
        add(body)

    for m in re.finditer(r"(?:زر|button)\s*[:=]?\s*[«\"'\[]([^»\"'\]]{2,40})[»\"'\]]", text, re.I):
        add(m.group(1).strip())

    # No keyword→button packs (hallucinate UI from prose).
    # If user listed no buttons, extract_dsl adds 1:1 labels from commands later.
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
    # progress/score threshold fragments only (not severity/stock mid-sentence)
    for m in re.finditer(r"((?:بنسبة\s*\d+|أكمل[^\n.]{0,40}\d+\s*%|progress[^\n.]{0,40}\d+)[^\n.]{0,40})", text, re.I):
        c = m.group(1).strip()
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



def _dynamic_intent(part: str) -> str | None:
    """
    Derive intent token purely from verbs/actions in the user clause.
    No domain packs — same function works for any business.
    """
    p = part.strip()
    pl = p.lower()
    # ordered: more specific multi-word first
    patterns: list[tuple[str, str]] = [
        (r"أنشأ|إنشاء|create\s+\w+|يسجل\s+[A-Z]", "create"),
        (r"قبول|يقبل|قبل\s+\w+|accept", "accept"),
        (r"رفض|يرفض|reject", "reject"),
        (r"بدأ\s+\w+|بدء\s+\w+|start\s+\w+", "start"),
        (r"عند\s+التسليم|تأكيد\s+التسليم|deliver|يغلق", "deliver"),
        (r"إلغاء|يلغي|ألغى|cancel|حذف|يحذف|drop", "cancel"),
        (r"تعيين|يعي[نّ]|assign|يربط", "assign"),
        (r"تم\s+الدفع|دفع|pay|سداد", "pay"),
        (r"تسجيل\s+وصول|check\s*in|checkin", "checkin"),
        (r"تسجيل\s+مغادرة|check\s*out|checkout", "checkout"),
        (r"طلب\s+استعارة|استعارة|borrow", "borrow"),
        (r"شكوى|complaint", "complaint"),
        (r"تقييم|review|rate", "review"),
        (r"حجز|book", "book"),
        (r"تسجيل|register|enroll", "register"),
        (r"طلب", "request"),
    ]
    for pat, intent in patterns:
        if re.search(pat, p, re.I):
            return intent
    return None


def _atomic_condition(part: str, buttons: list[ButtonNode]) -> ConditionExpr:
    part = part.strip()
    if not part:
        return ConditionExpr(left="signal", op="contains", right="", raw=part)

    # 1) explicit choice
    cm = re.search(r"(?:اختار|اختيار|يختار|choose|select)\s+(.+)", part, re.I)
    if cm:
        choice = cm.group(1).strip()
        choice = re.split(r"\s+(?:ثم|بعدها|then)\s+", choice, maxsplit=1)[0].strip()
        btn = _best_button_match(choice, buttons)
        if btn:
            return ConditionExpr(left="choice", op="eq", right=btn.callback_id, raw=f"{part}|label={btn.label}")
        if not re.search(r"\b(available|true|false|booked|paid|active|صحيح|خطأ)\b", choice, re.I):
            return ConditionExpr(left="choice", op="eq", right=choice[:60], raw=part)

    # 2) field comparisons (status يساوي booked, amount > 0)
    m = re.search(
        r"([A-Za-z_][A-Za-z0-9_]{1,40})\s*(?:يساوي|==|=|equals|equal to)\s*[«\"']?([A-Za-z0-9_\u0600-\u06FF]+)[»\"']?",
        part,
        re.I,
    )
    if m:
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="eq", right=m.group(2).strip(), raw=part)

    m = re.search(
        r"([A-Za-z_][A-Za-z0-9_]{1,40})\s*(?:!=|لا يساوي|not equals)\s*[«\"']?([A-Za-z0-9_\u0600-\u06FF]+)[»\"']?",
        part,
        re.I,
    )
    if m:
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="ne", right=m.group(2).strip(), raw=part)

    m = re.search(
        r"([A-Za-z_][A-Za-z0-9_]{1,40})\s*(?:>=|أكبر من أو يساوي|لا يقل عن)\s*(\d+(?:\.\d+)?)",
        part,
        re.I,
    )
    if m:
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="gte", right=m.group(2), raw=part)

    # field-to-field: capacity أكبر من enrolled
    m = re.search(
        r"([A-Za-z_][A-Za-z0-9_]{1,40})\s*(?:>|أكبر من|أكثر من)\s*([A-Za-z_][A-Za-z0-9_]{1,40})\b",
        part,
        re.I,
    )
    if m and not m.group(2).isdigit():
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="gt", right="@" + _ascii_ident(m.group(2)), raw=part)

    m = re.search(
        r"([A-Za-z_][A-Za-z0-9_]{1,40})\s*(?:>=|أكبر من أو يساوي|لا يقل عن)\s*([A-Za-z_][A-Za-z0-9_]{1,40})\b",
        part,
        re.I,
    )
    if m and not m.group(2).isdigit():
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="gte", right="@" + _ascii_ident(m.group(2)), raw=part)

    m = re.search(
        r"([A-Za-z_][A-Za-z0-9_]{1,40})\s*(?:<|أقل من)\s*([A-Za-z_][A-Za-z0-9_]{1,40})\b",
        part,
        re.I,
    )
    if m and not m.group(2).isdigit():
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="lt", right="@" + _ascii_ident(m.group(2)), raw=part)

    m = re.search(
        r"([A-Za-z_][A-Za-z0-9_]{1,40})\s*(?:>|أكبر من|أكثر من)\s*(\d+(?:\.\d+)?)",
        part,
        re.I,
    )
    if m:
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="gt", right=m.group(2), raw=part)

    m = re.search(
        r"([A-Za-z_][A-Za-z0-9_]{1,40})\s*(?:<=|أقل من أو يساوي)\s*(\d+(?:\.\d+)?)",
        part,
        re.I,
    )
    if m:
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="lte", right=m.group(2), raw=part)

    m = re.search(
        r"([A-Za-z_][A-Za-z0-9_]{1,40})\s*(?:<|أقل من)\s*(\d+(?:\.\d+)?)",
        part,
        re.I,
    )
    if m:
        return ConditionExpr(left=_ascii_ident(m.group(1)), op="lt", right=m.group(2), raw=part)

    # 3) boolean field flags: available / requires_rx / booked
    m2 = re.search(r"\b(available|requires_rx|paid|active|enabled|booked|confirmed|cancelled)\b", part, re.I)
    if m2:
        field = m2.group(1).lower()
        neg = bool(re.search(r"\b(لا|ليس|not|no|غير)\b", part, re.I))
        if neg:
            return ConditionExpr(left=field, op="eq", right="false", raw=part)
        return ConditionExpr(left=field, op="truthy", right="true", raw=part)

    # "لا توجد وصفة"
    if re.search(r"لا توجد|لا يوجد|بدون|missing", part, re.I):
        target = "has_prescription"
        if any(k in part for k in ("وصفة", "prescription", "rx")):
            target = "has_prescription"
        elif any(k in part for k in ("موعد", "appointment")):
            target = "has_appointment"
        return ConditionExpr(left=target, op="eq", right="false", raw=part)

    # 4) paid / success
    if _signal(part, "paid_success") or (
        _signal(part, "success") and any(k in _norm_text(part) for k in ("دفع", "pay", "paid", "سداد"))
    ):
        return ConditionExpr(left="paid", op="truthy", right="true", raw=part)
    if _signal(part, "success"):
        return ConditionExpr(left="success", op="truthy", right="true", raw=part)

    # 5) threshold
    num = _parse_number(part)
    if num and (_signal(part, "threshold") or _signal(part, "threshold_lt") or "%" in part or "نسبة" in part):
        op = "lte" if _signal(part, "threshold_lt") or "أقل" in part else "gte"
        left = "score" if any(k in part for k in ("درجة", "score", "نقاط")) else "progress"
        return ConditionExpr(left=left, op=op, right=num, raw=part)

    # 6) dynamic intent from clause verbs (not domain packs)
    intent = _dynamic_intent(part)
    if intent:
        return ConditionExpr(left="intent", op="eq", right=intent, raw=part)

    # 7) bare button match
    btn = _best_button_match(part, buttons)
    if btn and len(part) <= 40:
        return ConditionExpr(left="choice", op="eq", right=btn.callback_id, raw=f"{part}|label={btn.label}")

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
        # do not prefix field comparisons or boolean fields
        is_fieldish = bool(re.search(
            r"[A-Za-z_][A-Za-z0-9_]{1,40}\s*(?:أكبر من|أكثر من|أقل من|>|<|>=|<=|يساوي|==)",
            p,
        )) or bool(re.search(r"\b(available|requires_rx|paid|stock|capacity|enrolled|gpa)\b", p, re.I))
        if i > 0 and prefix and not is_fieldish and not re.search(r"(?:اختار|اختيار|choose|select)", p, re.I):
            fixed.append(prefix + p)
        else:
            fixed.append(p)
    return [_atomic_condition(p, buttons) for p in fixed], mode



def _resolve_create_target(eff_raw: str, entities: list[EntityNode]) -> str:
    """Prefer longest declared entity name appearing in effect text."""
    # 1) declared entities (longest first)
    names = sorted({e.name for e in entities if e.name}, key=len, reverse=True)
    for n in names:
        if n in eff_raw or n.lower() in _norm_text(eff_raw):
            return n
    # 2) CapWords in the effect text only (no domain name pack)
    caps = re.findall(r"\b([A-Z][a-zA-Z0-9]{2,40})\b", eff_raw)
    if caps:
        return max(caps, key=len)
    # 4) fuzzy from entity list via best match
    best = _best_entity_match(eff_raw, entities)
    return best or "record"


def _effects_from_clause(eff_raw: str, entities: list[EntityNode]) -> list[EffectExpr]:
    """Effects keep the user's literal wording in value/raw."""
    effects: list[EffectExpr] = []
    literal = eff_raw.strip()

    if re.search(r"يلغي|إلغاء|cancel|يحذف|حذف|drop|delete", eff_raw, re.I):
        val = "dropped" if re.search(r"حذف|drop|delete|يحذف", eff_raw, re.I) else "cancelled"
        effects.append(EffectExpr(kind="set", target="status", value=val, raw=literal))
        effects.append(EffectExpr(kind="reply", target="message", value=literal[:120], raw=literal))
    if re.search(r"يحدث|update|تعديل", eff_raw, re.I):
        # extract explicit status targets: assigned / in_transit / delivered / pending
        st = None
        for label in ("delivered", "in_transit", "assigned", "pending", "cancelled", "confirmed", "booked", "dropped"):
            if re.search(rf"\b{label}\b", eff_raw, re.I) or label.replace("_", " ") in eff_raw.lower():
                st = label
                break
        ar_map = [
            (r"assigned|يعي[نّ]|يربط", "assigned"),
            (r"in_transit|في\s*الطريق|قيد\s*التنفيذ", "in_transit"),
            (r"delivered|تم\s*التسليم|يغلق", "delivered"),
            (r"pending|قيد\s*الانتظار|للطابور", "pending"),
        ]
        if st is None:
            for pat, val in ar_map:
                if re.search(pat, eff_raw, re.I):
                    st = val
                    break
        if st:
            effects.append(EffectExpr(kind="set", target="status", value=st, raw=literal))
        else:
            effects.append(EffectExpr(kind="set", target="updated", value="true", raw=literal))
        effects.append(EffectExpr(kind="reply", target="message", value=literal[:120], raw=literal))
    # explicit status phrases even without يحدث
    if re.search(r"إلى\s*assigned|status\s*إلى\s*assigned|يعي[نّ].*assigned", eff_raw, re.I):
        if not any(e.target == "status" for e in effects):
            effects.append(EffectExpr(kind="set", target="status", value="assigned", raw=literal))
    if re.search(r"in_transit|إلى\s*in_transit", eff_raw, re.I):
        if not any(e.target == "status" and e.value == "in_transit" for e in effects):
            effects.append(EffectExpr(kind="set", target="status", value="in_transit", raw=literal))
    if re.search(r"delivered|إلى\s*delivered|عند\s*التسليم|تأكيد\s*التسليم|يغلق\s*الشحنة", eff_raw, re.I):
        if not any(e.target == "status" and e.value == "delivered" for e in effects):
            effects.append(EffectExpr(kind="set", target="status", value="delivered", raw=literal))
    if re.search(r"يرفض|رفض|reject|deny", eff_raw, re.I):
        effects.append(EffectExpr(kind="set", target="rejected", value="true", raw=literal))
        effects.append(EffectExpr(kind="reply", target="message", value=literal[:120], raw=literal))
    if re.search(r"ينبه|تنبيه|alert|notify", eff_raw, re.I):
        effects.append(EffectExpr(kind="set", target="alert_admin", value="true", raw=literal))
        effects.append(EffectExpr(kind="reply", target="message", value=literal[:120], raw=literal))

    # skip create when this effect is clearly a delete/cancel
    if _signal(eff_raw, "create_record") and not re.search(r"يحذف|حذف|يلغي|إلغاء|drop|delete|cancel", eff_raw, re.I):
        target = _resolve_create_target(eff_raw, entities)
        effects.append(EffectExpr(kind="create", target=target, value=literal[:80], raw=literal))
    # bare entity name after pay/register verbs counts as create (dynamic from CapWord/entities)
    elif re.search(r"\b([A-Z][a-zA-Z0-9]{2,40})\b", eff_raw) and not any(e.kind == "create" for e in effects):
        target = _resolve_create_target(eff_raw, entities)
        if target and target != "record":
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

    # Explicit rules section lines as extra clauses
    for line in _section_lines(text, "القواعد", "قواعد", "rules", "الشروط", "conditions"):
        body = _strip_bullet(line)
        if body and len(body) >= 6:
            clauses.append(body)

    for clause in clauses:
        clause = _strip_bullet(clause)
        if not clause:
            continue

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

        # Arabic soft conditional without ثم:
        # لو الطالب دفع بنجاح يفتح له الكورس
        # لو الدرجة أكبر من أو تساوي 60 يعتبر ناجح
        # لو السائق قبل الطلب تتغير الحالة إلى accepted
        m = re.search(
            r"(?:إذا|لو|if)\s+(?P<cond>.+?)\s+"
            r"(?P<eff>(?:يفتح|يعتبر|يعيد|يفعل|يسمح|يمنع|يرفض|يقبل|يحفظ|يسجل|يرسل|يعرض|"
            r"تتغير|يتغير|تصير|يصبح|ينب[ّ]?ه|ينبه|يرفض|يُخفى|يخفى|"
            r"enable|open|unlock|pass|fail|allow|deny|save|send|show|reject|alert|"
            r"change|set|update)\S*\s*.+)$",
            clause,
            re.I,
        )
        if m:
            cond_raw = m.group("cond").strip()
            eff_raw = m.group("eff").strip()
            conditions, mode = _conditions_from_clause(cond_raw, buttons)
            # numeric threshold inside condition: أكبر من أو تساوي 60
            tm = re.search(
                r"(?:أكبر من أو تساوي|أكبر من|أكثر من|لا يقل عن|>=|≥|at least|greater than or equal)\s*(\d+(?:\.\d+)?)",
                cond_raw,
                re.I,
            )
            if tm:
                left = "score" if any(k in cond_raw for k in ("درجة", "score", "نقاط", "تقييم")) else "progress"
                conditions = [ConditionExpr(left=left, op="gte", right=tm.group(1), raw=cond_raw[:80])]
            tm2 = re.search(
                r"(?:أقل من أو تساوي|أقل من|<=|≤|less than)\s*(\d+(?:\.\d+)?)",
                cond_raw,
                re.I,
            )
            if tm2 and not tm:
                left = "score" if any(k in cond_raw for k in ("درجة", "score", "نقاط", "تقييم")) else "progress"
                conditions = [ConditionExpr(left=left, op="lt", right=tm2.group(1), raw=cond_raw[:80])]
            if not conditions:
                conditions = [ConditionExpr(left="signal", op="truthy", right="", raw=cond_raw[:80])]
            effects = _effects_from_clause(eff_raw, entities)
            # status assignment: تتغير الحالة إلى accepted
            sm = re.search(
                r"(?:الحالة|status)\s*(?:إلى|to|=)\s*([A-Za-z_][A-Za-z0-9_]{1,32})",
                eff_raw,
                re.I,
            )
            if sm:
                effects.insert(
                    0,
                    EffectExpr(kind="set", target="status", value=sm.group(1).lower(), raw=eff_raw[:80]),
                )
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
        # only true progress/score thresholds — not severity/stock residues
        if m and (
            "%" in clause or "نسبة" in clause
            or re.search(r"progress|score|درجة|علاج|ساعات|إكمال|أكمل|نقاط", clause, re.I)
        ):
            num = m.group(1)
            rest = (m.group(2) or "").strip()
            op = "lte" if any(k in clause for k in ("أقل", "less")) else "gte"
            left = "score" if any(k in clause for k in ("درجة", "score", "نقاط")) else "progress"
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
            if re.search(r"delivered|عند\s*التسليم|تأكيد\s*التسليم", clause, re.I):
                cr.effects.append(EffectExpr(kind="set", target="status", value="delivered", raw=clause[:80]))
                # also intent condition so /deliver triggers it
                if not cr.conditions:
                    cr.conditions = [ConditionExpr(left="intent", op="eq", right="deliver", raw="deliver")]
                    cr.kind = "conditional"
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


def _flows_from_text(text: str) -> list[OperationNode]:
    """Parse التدفقات section into wizard operations."""
    ops: list[OperationNode] = []
    lines = _section_lines(text, "التدفقات", "التدفق", "flows", "wizards")
    if not lines:
        return ops
    current: dict | None = None
    steps: list[dict] = []

    def flush() -> None:
        nonlocal current, steps
        if not current:
            return
        ops.append(OperationNode(
            kind="wizard",
            name=str(current.get("id") or "flow"),
            inputs=list(current.get("fields") or []),
            outputs=[str(current.get("entity") or "record")],
            meta={
                "command": current.get("id"),
                "entity": current.get("entity") or "record",
                "steps": list(steps),
                "kind": "collect",
                "prefill_from_button": "",
            },
        ))
        current, steps = None, []

    for line in lines:
        body = _strip_bullet(line)
        if not body:
            continue
        m = re.match(
            r"^(?P<id>[A-Za-z][A-Za-z0-9_]{1,32})(?:\s*@(?P<ent>[A-Za-z][A-Za-z0-9_]{0,32}))?\s*:?\s*(?P<fields>.*)$",
            body,
        )
        if m and not body.lstrip().startswith("•") and ":" in body.replace("：", ":"):
            # only treat as flow header when has id-like start
            if re.match(r"^[A-Za-z]", body):
                flush()
                fields = [x.strip() for x in re.split(r"[,،]", m.group("fields") or "") if x.strip() and " " not in x.strip()[:20]]
                # fields may include prompts after — keep only tokens
                fields = [f for f in fields if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", f)]
                current = {
                    "id": m.group("id"),
                    "entity": m.group("ent") or "record",
                    "fields": fields,
                }
                steps = [{"key": f, "prompt": f"أرسل {f}"} for f in fields]
                continue
        m2 = re.match(
            r"^[•\-]?\s*(?P<key>[A-Za-z_][A-Za-z0-9_]{0,32})\s*:\s*(?P<prompt>.+)$",
            body,
        )
        if m2 and current is not None:
            key, prompt = m2.group("key"), m2.group("prompt").strip()
            found = False
            for st in steps:
                if st.get("key") == key:
                    st["prompt"] = prompt
                    found = True
                    break
            if not found:
                steps.append({"key": key, "prompt": prompt})
            if key not in (current.get("fields") or []):
                current.setdefault("fields", []).append(key)
    flush()
    return ops



def extract_dsl(text: str) -> DSLProgram:
    full = (text or "").strip()
    if len(full) > 200_000:
        full = full[:200_000]
    entities = _entities_from_text(full)
    commands = _commands_from_text(full)
    buttons = _buttons_from_text(full)
    relations = _relations_from_text(full, entities)
    # No domain-specific Order/Item relation templates.

    operations = _operations_from_text(full, buttons)
    rules = _rules_from_text(full, entities, buttons)
    t = full.lower()
    wants_db = any(k in full or k in t for k in ("قاعدة بيانات", "database", "يحفظ", "تخزين", "sqlite", "postgres"))
    wants_files = any(k in full or k in t for k in ("صورة", "ملف", "رفع", "photo", "file", "upload", "document"))
    h = hashlib.sha256(full.encode("utf-8")).hexdigest()[:16]
    # Structural buttons from commands when user did not list any buttons.
    # Not a domain pack: each button maps 1:1 to an extracted command.
    if not buttons:
        seen_btn: set[str] = set()
        for c in commands:
            if c.name in ("start", "help"):
                continue
            label = (c.description or c.name or "").strip()
            if not label or label in seen_btn or len(label) > 48:
                continue
            seen_btn.add(label)
            buttons.append(ButtonNode(label=label, callback_id=f"cmd:{c.name}"))

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
