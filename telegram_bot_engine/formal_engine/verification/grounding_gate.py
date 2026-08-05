"""
Grounding gate — post-extraction text fidelity check.

HARD RULE: nothing may survive extraction unless it is grounded in the
user specification. Structural minima (/start, /help) are the only
exceptions.

This gate does NOT invent content. It only drops ungrounded items and
records what was removed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from ..dsl.ast import (
    ButtonNode,
    CommandNode,
    DSLProgram,
    EntityNode,
    RuleNode,
)

# Only structural minima allowed without literal mention
_STRUCTURAL_CMDS = frozenset({"start", "help"})


@dataclass
class GroundingReport:
    ok: bool = True
    removed_commands: list[str] = field(default_factory=list)
    removed_entities: list[str] = field(default_factory=list)
    removed_buttons: list[str] = field(default_factory=list)
    removed_rules: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "removed_commands": list(self.removed_commands),
            "removed_entities": list(self.removed_entities),
            "removed_buttons": list(self.removed_buttons),
            "removed_rules": list(self.removed_rules),
            "warnings": list(self.warnings),
        }


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي")
    return s


def _text_has_cmd(text_n: str, raw: str, name: str, desc: str = "") -> bool:
    """Command grounded via /name, name token, or description phrase in user text."""
    n = (name or "").lower().strip()
    if not n:
        return False
    if n in _STRUCTURAL_CMDS:
        return True
    if re.search(rf"/{re.escape(n)}\b", raw, re.I):
        return True
    if re.search(rf"/{re.escape(n)}\b", text_n):
        return True
    if re.search(rf"(?:^|[\s,|]){re.escape(n)}(?:\s*[-–—:]|\s|$)", text_n, re.M):
        return True
    parts = [p for p in n.split("_") if len(p) >= 3]
    if len(parts) >= 2 and all(p in text_n for p in parts):
        return True
    d = (desc or "").strip()
    if d and len(d) >= 2:
        if d in raw or _norm(d) in text_n:
            return True
        toks = [t for t in re.split(r"\s+", d) if len(t) >= 3]
        if toks and sum(1 for t in toks if _norm(t) in text_n or t in raw) >= max(1, len(toks) - 1):
            return True
    for part in n.split("_"):
        if len(part) >= 4 and re.search(rf"\b{re.escape(part)}\b", text_n):
            return True
    # Common AR/EN intent synonyms (must still appear in user text)
    synonyms = {
        "register": ("تسجيل", "يسجل", "register", "signup"),
        "new_order": ("طلب جديد", "اوردر", "order", "طلب"),
        "my_orders": ("طلباتي", "اوردرات", "my orders"),
        "menu": ("منيو", "menu", "قائمه الطعام", "قائمة الطعام"),
        "track": ("تتبع", "track"),
        "accept_order": ("يقبل", "قبول", "accept"),
        "admin": ("ادمن", "أدمن", "admin", "مشرف"),
        "stats": ("احصائ", "إحصائ", "stats"),
        "add_item": ("صنف", "منتج", "add item"),
        "book": ("حجز", "book"),
    }
    for key, words in synonyms.items():
        if key == n or key in n:
            if any(w in raw for w in words) or any(_norm(w) in text_n for w in words):
                return True
    return False


def _text_has_entity(text_n: str, raw: str, name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    if re.search(rf"\b{re.escape(n)}\b", raw):
        return True
    if n.lower() in text_n:
        return True
    # Arabic free-form nouns → English entity names
    ar_map = {
        "customer": ("عميل", "عملاء", "customer"),
        "driver": ("سائق", "سواق", "driver"),
        "order": ("طلب", "اوردر", "order"),
        "task": ("مهمة", "مهام", "task"),
        "product": ("صنف", "منتج", "product", "item"),
        "patient": ("مريض", "patient"),
        "doctor": ("طبيب", "doctor"),
        "appointment": ("موعد", "appointment"),
        "user": ("مستخدم", "user"),
    }
    key = n.lower()
    for stem, words in ar_map.items():
        if stem in key:
            if any(w in raw for w in words) or any(_norm(w) in text_n for w in words):
                return True
    return False


def _text_has_button(text_n: str, raw: str, label: str) -> bool:
    lab = (label or "").strip()
    if not lab or len(lab) < 2:
        return False
    if lab in raw:
        return True
    ln = _norm(lab)
    if ln in text_n:
        return True
    # drop leading ال
    if ln.startswith("ال") and len(ln) > 4 and ln[2:] in text_n:
        return True
    toks = [t for t in re.split(r"\s+", lab) if len(t) >= 3]
    if toks and all(_norm(t) in text_n or _norm(t).lstrip("ال") in text_n for t in toks):
        return True
    return False


def _text_has_rule(text_n: str, raw: str, rule: RuleNode) -> bool:
    body = (getattr(rule, "raw", None) or "").strip()
    if not body:
        return False
    if body in raw:
        return True
    # normalized containment of a long enough core
    core = _norm(body)
    if len(core) >= 12 and core[:40] in text_n:
        return True
    # key fragments: لو/if + one effect word from raw
    if re.search(r"(?:لو|إذا|if)\s+", body, re.I):
        frag = _norm(re.sub(r"\s+", " ", body))[:50]
        if frag and frag in text_n:
            return True
        # soft: at least 3 significant tokens from rule appear in text
        toks = [t for t in re.split(r"\s+", core) if len(t) >= 3][:6]
        if len(toks) >= 3 and sum(1 for t in toks if t in text_n) >= max(3, len(toks) - 1):
            return True
    return False


def apply_grounding_gate(program: DSLProgram, user_text: str) -> tuple[DSLProgram, GroundingReport]:
    """
    Filter DSLProgram to text-grounded surface only.

    Returns (cleaned_program, report). Never raises on empty input —
    returns empty program with ok=True and warnings.
    """
    raw = user_text or ""
    text_n = _norm(raw)
    report = GroundingReport()

    if not raw.strip():
        report.warnings.append("empty_user_text")
        empty = replace(
            program,
            commands=[],
            entities=[],
            buttons=[],
            rules=[],
            relations=[],
        )
        return empty, report

    # Commands
    kept_cmds: list[CommandNode] = []
    seen_cmd: set[str] = set()
    for c in list(program.commands or []):
        name = (c.name or "").lower()
        if name in seen_cmd:
            continue
        desc = getattr(c, "description", "") or ""
        if _text_has_cmd(text_n, raw, name, desc):
            kept_cmds.append(c)
            seen_cmd.add(name)
        else:
            report.removed_commands.append(name)
    # ensure structural minima after filter
    if "start" not in seen_cmd:
        kept_cmds.insert(0, CommandNode(name="start", description="تشغيل البوت"))
        seen_cmd.add("start")
        report.warnings.append("injected_structural:start")
    if "help" not in seen_cmd:
        kept_cmds.append(CommandNode(name="help", description="المساعدة"))
        seen_cmd.add("help")
        report.warnings.append("injected_structural:help")

    # Entities
    kept_ents: list[EntityNode] = []
    seen_ent: set[str] = set()
    for e in list(program.entities or []):
        key = (e.name or "").lower()
        if key in seen_ent:
            continue
        if _text_has_entity(text_n, raw, e.name):
            kept_ents.append(e)
            seen_ent.add(key)
        else:
            report.removed_entities.append(e.name)

    # Buttons
    kept_btns: list[ButtonNode] = []
    seen_btn: set[str] = set()
    for b in list(program.buttons or []):
        lab = (b.label or "").strip()
        if lab in seen_btn:
            continue
        if _text_has_button(text_n, raw, lab):
            kept_btns.append(b)
            seen_btn.add(lab)
        else:
            report.removed_buttons.append(lab)

    # Rules
    kept_rules: list[RuleNode] = []
    for r in list(program.rules or []):
        if _text_has_rule(text_n, raw, r):
            kept_rules.append(r)
        else:
            report.removed_rules.append((getattr(r, "raw", None) or r.name or "")[:80])

    # Relations: keep only if entity still present (or no entity binding)
    kept_ent_names = {e.name.lower() for e in kept_ents}
    kept_rels = []
    for rel in list(program.relations or []):
        ent = getattr(rel, "entity", None)
        if ent is None:
            kept_rels.append(rel)
            continue
        if (ent.name or "").lower() in kept_ent_names:
            kept_rels.append(rel)

    cleaned = replace(
        program,
        commands=kept_cmds,
        entities=kept_ents,
        buttons=kept_btns,
        rules=kept_rules,
        relations=kept_rels,
    )

    dropped = (
        len(report.removed_commands)
        + len(report.removed_entities)
        + len(report.removed_buttons)
        + len(report.removed_rules)
    )
    if dropped:
        report.warnings.append(f"grounding_dropped:{dropped}")
    # ok stays True — gate filters, does not hard-fail the pipeline
    report.ok = True
    return cleaned, report
