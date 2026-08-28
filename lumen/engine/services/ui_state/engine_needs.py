"""Derive what the *engine* still needs from a user goal.

Primary: language_understanding.build_question_plan (same as message_router L3).
Fallback: dynamic_planner intent + feature heuristics.

UI must render buttons/prompts from NeedPlan — not invent parallel questionnaires.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NeedChoice:
    choice_id: str  # short id for callback arg (<=12)
    label: str
    value: str


@dataclass
class EngineNeed:
    slot: str
    text: str
    choices: list[NeedChoice] = field(default_factory=list)
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "text": self.text,
            "required": self.required,
            "choices": [
                {"choice_id": c.choice_id, "label": c.label, "value": c.value}
                for c in self.choices
            ],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EngineNeed":
        choices = []
        for c in raw.get("choices") or []:
            if not isinstance(c, dict):
                continue
            choices.append(
                NeedChoice(
                    choice_id=str(c.get("choice_id") or "")[:12],
                    label=str(c.get("label") or "")[:40],
                    value=str(c.get("value") or "")[:200],
                )
            )
        return cls(
            slot=str(raw.get("slot") or "")[:40],
            text=str(raw.get("text") or "")[:300],
            choices=choices,
            required=bool(raw.get("required", True)),
        )


@dataclass
class NeedPlan:
    needs: list[EngineNeed] = field(default_factory=list)
    intent_kind: str = ""
    source: str = ""  # lu | planner_fallback

    def to_list(self) -> list[dict[str, Any]]:
        return [n.to_dict() for n in self.needs]


# Known choice sets for common slots (engine-aligned, used when LU has no options)
_SLOT_CHOICES: dict[str, list[NeedChoice]] = {
    "payment": [
        NeedChoice("pay_vod", "فودافون كاش", "vodafone_cash"),
        NeedChoice("pay_wal", "محفظة", "wallet"),
        NeedChoice("pay_tg", "تيليجرام فقط", "telegram_only"),
        NeedChoice("pay_none", "بدون دفع", "none"),
    ],
    "product_or_category": [
        NeedChoice("cat_cloth", "ملابس", "clothes"),
        NeedChoice("cat_elec", "إلكترونيات", "electronics"),
        NeedChoice("cat_food", "أكل", "food"),
        NeedChoice("cat_other", "أخرى (اكتب)", "other"),
    ],
    "audience": [
        NeedChoice("aud_beg", "مبتدئين", "beginners"),
        NeedChoice("aud_pro", "محترفين", "pros"),
        NeedChoice("aud_all", "الجميع", "everyone"),
    ],
    "storage": [
        NeedChoice("st_sql", "SQLite", "sqlite"),
        NeedChoice("st_mem", "ذاكرة فقط", "memory"),
    ],
    "language": [
        NeedChoice("lang_ar", "عربي", "ar"),
        NeedChoice("lang_en", "English", "en"),
    ],
}


_AR_TEXT = {
    "payment": "ما طريقة الدفع المطلوبة؟",
    "product_or_category": "ما فئة المنتجات؟",
    "audience": "من الجمهور المستهدف؟",
    "storage": "أين تُحفظ البيانات؟",
    "language": "لغة واجهة البوت؟",
    "bot_name": "ما اسم البوت؟",
    "commands": "ما الأوامر الأساسية؟",
}


def _choices_for_slot(slot: str) -> list[NeedChoice]:
    return list(_SLOT_CHOICES.get(slot) or [])


def _from_language_understanding(goal: str, *, user_id: int | None = None) -> NeedPlan | None:
    try:
        from lumen.engine.spec_core.language_understanding import (
            analyze_intent,
            build_question_plan,
            understand,
        )
    except Exception:
        return None
    try:
        lu = understand(goal)
        intent = analyze_intent(goal, lu=lu)
        qp = build_question_plan(
            goal,
            intent=intent,
            lu=lu,
            user_id=user_id,
            remember=False,
            max_questions=5,
        )
        if not qp or not getattr(qp, "questions", None):
            # still return intent for UI
            kind = ""
            try:
                kind = str(getattr(getattr(intent, "primary", None), "intent", "") or "")
            except Exception:
                kind = ""
            return NeedPlan(needs=[], intent_kind=kind, source="lu_empty")
        needs: list[EngineNeed] = []
        for i, q in enumerate(list(qp.questions)[:5]):
            slot = str(getattr(q, "slot", None) or getattr(q, "id", None) or f"q{i}")
            text = str(getattr(q, "text", "") or _AR_TEXT.get(slot) or slot)
            choices = _choices_for_slot(slot)
            # LU may expose options
            raw_opts = getattr(q, "options", None) or getattr(q, "choices", None) or []
            if raw_opts and not choices:
                for j, opt in enumerate(list(raw_opts)[:6]):
                    label = str(opt if not isinstance(opt, dict) else opt.get("label") or opt)
                    val = str(opt if not isinstance(opt, dict) else opt.get("value") or label)
                    choices.append(NeedChoice(f"o{j}", label[:40], val[:200]))
            needs.append(EngineNeed(slot=slot, text=text, choices=choices, required=True))
        kind = ""
        try:
            kind = str(getattr(getattr(intent, "primary", None), "intent", "") or "")
        except Exception:
            pass
        return NeedPlan(needs=needs, intent_kind=kind, source="lu")
    except Exception:
        logger.debug("LU need plan failed", exc_info=True)
        return None


def _from_planner_fallback(goal: str) -> NeedPlan:
    """When LU package is absent — use multi_agent dynamic_planner signals."""
    needs: list[EngineNeed] = []
    kind = "general_app"
    try:
        from lumen.engine.services.multi_agent.dynamic_planner import (
            classify_intent,
            extract_features,
        )

        intent = classify_intent(goal)
        kind = intent.kind
        feats = extract_features(goal) if callable(extract_features) else []
    except Exception:
        feats = []
        try:
            from lumen.engine.services.multi_agent.dynamic_planner import classify_intent

            kind = classify_intent(goal).kind
        except Exception:
            pass

    text = (goal or "").lower()
    # Heuristic needs only when signals present in goal but slot value still vague
    if any(k in text for k in ("متجر", "shop", "store", "بيع", "منتج")):
        if "دفع" not in text and "payment" not in text and "فودافون" not in text:
            needs.append(
                EngineNeed(
                    "payment",
                    _AR_TEXT["payment"],
                    _choices_for_slot("payment"),
                )
            )
        if not any(k in text for k in ("ملابس", "إلكترون", "اكل", "أكل", "منتج")):
            needs.append(
                EngineNeed(
                    "product_or_category",
                    _AR_TEXT["product_or_category"],
                    _choices_for_slot("product_or_category"),
                )
            )
    if any(k in text for k in ("إشعار", "اشعار", "broadcast", "notify")):
        if "جمهور" not in text and "subscribe" not in text:
            needs.append(
                EngineNeed("audience", _AR_TEXT["audience"], _choices_for_slot("audience"))
            )
    if kind == "telegram_bot" and len((goal or "").strip()) < 40:
        needs.append(
            EngineNeed(
                "commands",
                "ما الأوامر التي تريدها؟ (مثال: /start /help /order)",
                [],
            )
        )
    return NeedPlan(needs=needs, intent_kind=kind, source="planner_fallback")


def analyze_needs(goal: str, *, user_id: int | None = None) -> NeedPlan:
    goal = (goal or "").strip()
    if not goal:
        return NeedPlan(needs=[], source="empty")
    plan = _from_language_understanding(goal, user_id=user_id)
    if plan is not None and plan.source.startswith("lu"):
        return plan
    return _from_planner_fallback(goal)


def remaining_needs(plan_needs: list[dict[str, Any]], slots: dict[str, str]) -> list[EngineNeed]:
    """Needs whose slot is not yet filled in state.slots."""
    out: list[EngineNeed] = []
    for raw in plan_needs:
        n = EngineNeed.from_dict(raw) if isinstance(raw, dict) else raw
        if not n.slot:
            continue
        if (slots.get(n.slot) or "").strip():
            continue
        out.append(n)
    return out


def apply_choice_to_slots(
    slots: dict[str, str], need: EngineNeed, choice_id: str
) -> dict[str, str]:
    slots = dict(slots)
    for c in need.choices:
        if c.choice_id == choice_id:
            slots[need.slot] = c.value
            if c.value == "other":
                slots["awaiting_text"] = "1"
                slots["awaiting_slot"] = need.slot
            return slots
    return slots


def enrich_description(base: str, slots: dict[str, str]) -> str:
    """Merge answered slots into generation request string."""
    base = (base or "").strip()
    extra = []
    for k, v in slots.items():
        if k in {"bot_type", "bot_description", "awaiting_text", "awaiting_slot", "confirmed", "needs_json"}:
            continue
        if v:
            extra.append(f"{k}: {v}")
    if not extra:
        return base
    return (base + "\n" + " | ".join(extra)).strip()
