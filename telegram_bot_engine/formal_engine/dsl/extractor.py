"""
Extract Custom DSL (Relations & Operations) from user natural language.
No domain packs. Text → logical equations only.
"""

from __future__ import annotations

import hashlib
import re

from .ast import (
    ActionNode,
    DSLProgram,
    EntityNode,
    OperationNode,
    RelationNode,
    RequiresNode,
)


def _slug(s: str) -> str:
    s = re.sub(r"\s+", "_", (s or "").strip())
    s = re.sub(r"[^\w]+", "_", s, flags=re.UNICODE)
    return s.strip("_")[:48] or "x"


def _entities_from_text(text: str) -> list[EntityNode]:
    """Entity(Name) from explicit mentions and noun signals."""
    found: list[EntityNode] = []
    seen: set[str] = set()

    def add(name: str, attrs: list[str] | None = None) -> None:
        n = _slug(name)
        if not n or n.lower() in seen or len(n) < 2:
            return
        # reject pure verbs / noise
        if n.lower() in ("start", "help", "bot", "telegram", "user_text"):
            return
        seen.add(n.lower())
        found.append(EntityNode(name=n[:1].upper() + n[1:], attributes=list(attrs or [])))

    # explicit: كيان X / entity X / نموذج X / جدول X
    for m in re.finditer(
        r"(?:كيان|نموذج|جدول|entity|model|table)\s+[«\"']?([A-Za-z\u0600-\u06ff][\w\u0600-\u06ff]{1,40})[»\"']?",
        text,
        re.I,
    ):
        add(m.group(1))

    # Latin CapWords
    for m in re.finditer(r"\b([A-Z][a-zA-Z0-9]{2,30})\b", text):
        add(m.group(1))

    # Arabic noun-like after "يحفظ/يخزن/يسجل"
    for m in re.finditer(
        r"(?:يحفظ|يخزن|يسجل|store|save|record)\s+([^\n،,]{2,40})",
        text,
        re.I,
    ):
        tok = m.group(1).strip().split()[0]
        add(tok)

    return found


def _relations_from_text(text: str, entities: list[EntityNode]) -> list[RelationNode]:
    """
    Build Entity -> Requires -> Action chains from text patterns.
    Example target:
      Entity(Appointment) -> Requires(User, Time) -> Action(ValidateAvailability)
    """
    relations: list[RelationNode] = []
    ent_names = {e.name.lower(): e for e in entities}

    # Pattern: X يحتاج/يتطلب Y و Z
    for m in re.finditer(
        r"([A-Za-z\u0600-\u06ff][\w\u0600-\u06ff]{1,30})\s+"
        r"(?:يحتاج|يتطلب|يتطلب وجود|requires|needs)\s+"
        r"([^\n.]{3,80})",
        text,
        re.I,
    ):
        ename = _slug(m.group(1))
        ops = [ _slug(p) for p in re.split(r"[,، و&]+", m.group(2)) if _slug(p) ]
        ent = ent_names.get(ename.lower()) or EntityNode(name=ename[:1].upper() + ename[1:])
        relations.append(
            RelationNode(
                entity=ent,
                requires=RequiresNode(operands=ops),
                action=None,
                raw=m.group(0)[:120],
            )
        )

    # Pattern: عند X يتم Y / when X then Y → Action
    for m in re.finditer(
        r"(?:عند|عندما|when)\s+([^\n،,]{3,50})\s+(?:يتم|يقوم|then|do)\s+([^\n.]{3,60})",
        text,
        re.I,
    ):
        act = _slug(m.group(2))
        relations.append(
            RelationNode(
                entity=None,
                requires=RequiresNode(operands=[_slug(m.group(1))]),
                action=ActionNode(name=act),
                raw=m.group(0)[:120],
            )
        )

    # Pattern: يتحقق من / validate X
    for m in re.finditer(
        r"(?:يتحقق من|التحقق من|validate|check)\s+([^\n،.]{2,40})",
        text,
        re.I,
    ):
        target = _slug(m.group(1))
        relations.append(
            RelationNode(
                entity=ent_names.get(target.lower()),
                requires=None,
                action=ActionNode(name=f"Validate{_slug(target)[:1].upper() + _slug(target)[1:]}"),
                raw=m.group(0)[:120],
            )
        )

    # Attach default Action(Create/List) per entity if no action yet
    covered = { (r.entity.name.lower() if r.entity else "") for r in relations }
    for e in entities:
        if e.name.lower() not in covered:
            relations.append(
                RelationNode(
                    entity=e,
                    requires=RequiresNode(operands=list(e.attributes) or ["id"]),
                    action=ActionNode(name=f"Manage{e.name}"),
                    raw=f"Entity({e.name})",
                )
            )
    return relations


def _operations_from_text(text: str) -> list[OperationNode]:
    """
    Operations from logical cues in text:
      repetition → loop
      decision   → decision
      storage    → store
      input      → receive
      output     → emit
    """
    ops: list[OperationNode] = []
    t = text.lower()

    # repetition / loops
    if any(k in text or k in t for k in ("تكرار", "لكل", " forevery", "for each", "loop", "عدة مرات", "قائمة من")):
        ops.append(
            OperationNode(
                kind="loop",
                name="IterateItems",
                inputs=["items"],
                outputs=["item"],
                meta={"signal": "repetition"},
            )
        )

    # decisions / branches
    if any(k in text or k in t for k in ("إذا", "لو", "أما إذا", "otherwise", "if ", "else", "اختيار", "قرر")):
        ops.append(
            OperationNode(
                kind="decision",
                name="BranchOnChoice",
                inputs=["choice"],
                outputs=["branch"],
                meta={"signal": "decision"},
            )
        )

    # storage
    if any(k in text or k in t for k in ("يحفظ", "تخزين", "قاعدة بيانات", "store", "save", "database", "يسجل")):
        ops.append(
            OperationNode(
                kind="store",
                name="PersistEntity",
                inputs=["entity", "fields"],
                outputs=["id"],
                meta={"signal": "storage"},
            )
        )

    # receive (commands / buttons / input)
    if any(k in text or k in t for k in ("أمر", "أوامر", "/start", "زر", "أزرار", "command", "button", "يرسل", "يطلب")):
        ops.append(
            OperationNode(
                kind="receive",
                name="ReceiveInput",
                inputs=["update"],
                outputs=["payload"],
                meta={"signal": "input"},
            )
        )

    # emit (replies)
    if any(k in text or k in t for k in ("يرسل", "يعرض", "رد", "reply", "send", "message")):
        ops.append(
            OperationNode(
                kind="emit",
                name="EmitReply",
                inputs=["text"],
                outputs=[],
                meta={"signal": "output"},
            )
        )

    # numbered steps → sequential compute ops
    for i, m in enumerate(
        re.finditer(r"(?:^|\n)\s*(?:\d+|[\u0660-\u0669]+)[\.\)\-\:]\s*([^\n]{5,120})", text)
    ):
        label = m.group(1).strip()
        ops.append(
            OperationNode(
                kind="compute",
                name=f"Step{i+1}_{_slug(label)[:20]}",
                inputs=["context"],
                outputs=["context"],
                body_refs=[label],
                meta={"ordinal": i + 1, "label": label[:120]},
            )
        )

    return ops


def extract_dsl(text: str) -> DSLProgram:
    """Natural language → DSLProgram (Relations & Operations)."""
    full = (text or "").strip()
    if len(full) > 200_000:
        full = full[:200_000]
    entities = _entities_from_text(full)
    relations = _relations_from_text(full, entities)
    operations = _operations_from_text(full)
    h = hashlib.sha256(full.encode("utf-8")).hexdigest()[:16]
    return DSLProgram(
        relations=relations,
        operations=operations,
        entities=entities,
        source_hash=h,
    )
