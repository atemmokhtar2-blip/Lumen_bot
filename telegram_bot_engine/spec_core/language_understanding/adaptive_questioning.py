"""Layer 3 — Adaptive Questioning Engine (zero-AI).

Builds a priority-ordered question queue from:
  - what Layer-2 already knows (skip filled slots)
  - user skill (beginner vs expert wording)
  - missing required/optional checklist slots
  - critical-first priority (purpose → core feature → payments → polish)

Never asks about facts already present in entities / signatures.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .intent_analysis import IntentAnalysis, analyze_intent
from .engine import LanguageUnderstandingResult, understand

_DATA = Path(__file__).resolve().parent / "data"


@dataclass
class AdaptiveQuestion:
    id: str
    text: str
    slot: str
    priority: int
    can_skip: bool
    choices: list[str] = field(default_factory=list)
    intent_scope: list[str] = field(default_factory=list)
    reason: str = ""  # why this question was selected

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "slot": self.slot,
            "priority": self.priority,
            "can_skip": self.can_skip,
            "choices": list(self.choices),
            "intent_scope": list(self.intent_scope),
            "reason": self.reason,
        }


@dataclass
class QuestionPlan:
    questions: list[AdaptiveQuestion]
    answers_known: dict[str, Any]
    skill_level: str
    language: str
    primary_intent: str | None
    should_block_generation: bool
    summary_ar: str
    summary_en: str
    intent: IntentAnalysis | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "questions": [q.to_dict() for q in self.questions],
            "answers_known": self.answers_known,
            "skill_level": self.skill_level,
            "language": self.language,
            "primary_intent": self.primary_intent,
            "should_block_generation": self.should_block_generation,
            "summary_ar": self.summary_ar,
            "summary_en": self.summary_en,
            "intent": self.intent.to_dict() if self.intent else None,
        }

    @property
    def next_question(self) -> AdaptiveQuestion | None:
        return self.questions[0] if self.questions else None

    def format_prompt(self, *, max_questions: int = 4) -> str:
        """Human-readable multi-question prompt for Telegram."""
        if not self.questions:
            return ""
        lang = self.language
        lines: list[str] = []
        if lang.startswith("ar"):
            lines.append("عشان أبني البوت صح، محتاج أوضح النقاط دي:")
        else:
            lines.append("To build the bot correctly, I need a few details:")
        for i, q in enumerate(self.questions[:max_questions], 1):
            lines.append(f"{i}) {q.text}")
            if q.choices:
                lines.append("   • " + " | ".join(q.choices[:6]))
        if any(q.can_skip for q in self.questions[:max_questions]):
            if lang.startswith("ar"):
                lines.append("\n(يمكنك تخطي الاختياري بـ /skip)")
            else:
                lines.append("\n(Optional ones can be skipped with /skip)")
        return "\n".join(lines)


@lru_cache(maxsize=1)
def _bank() -> dict[str, dict]:
    path = _DATA / "question_bank.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _is_ar(lang: str) -> bool:
    return (lang or "").startswith("ar")


def _known_answers(intent: IntentAnalysis, lu: LanguageUnderstandingResult) -> dict[str, Any]:
    """Facts already extracted — never ask these again."""
    ent = lu.entities
    known: dict[str, Any] = {}
    if intent.primary:
        known["bot_purpose"] = intent.primary.intent
    if ent.product:
        known["product_or_category"] = ent.product
    elif ent.category:
        known["product_or_category"] = ent.category
    if ent.payment_methods:
        known["payment"] = list(ent.payment_methods)
    if ent.wants_delivery:
        known["delivery"] = True
    if ent.wants_discounts:
        known["discounts"] = True
    if ent.security_checks:
        known["security_scope"] = list(ent.security_checks)
    if ent.target_domain or ent.target_url or ent.target_ip:
        known["target_host"] = ent.target_domain or ent.target_url or ent.target_ip
    if ent.course_topic:
        known["course_scope"] = ent.course_topic
    if ent.tech_stack:
        known["connectivity"] = list(ent.tech_stack)
        known["ops_scope"] = list(ent.tech_stack)
    if intent.primary and intent.primary.intent == "moderation":
        known["mod_actions"] = intent.primary.evidence[:4] or True
    if intent.primary and intent.primary.intent in {"booking", "clinic"}:
        known["booking_type"] = intent.primary.intent
    if intent.primary and intent.primary.intent == "restaurant":
        known["menu_or_orders"] = True
    if intent.primary and intent.primary.intent == "gaming":
        known["game_loop"] = True
    if intent.primary and intent.primary.intent == "crm":
        known["pipeline"] = True
    if intent.primary and intent.primary.intent in {"saas", "subscriptions"}:
        known["plans"] = True
    if intent.primary and intent.primary.intent == "tickets":
        # audience still often unknown
        pass
    return known


def _slot_filled(slot: str, known: dict[str, Any], intent: IntentAnalysis) -> bool:
    if slot in known and known[slot] not in (None, "", [], False):
        return True
    # checklist filled_slots from L2
    if intent.filled_slots.get(slot):
        return True
    return False


def build_question_plan(
    text: str,
    *,
    intent: IntentAnalysis | None = None,
    lu: LanguageUnderstandingResult | None = None,
    max_questions: int = 5,
    include_optional: bool | None = None,
) -> QuestionPlan:
    """Build adaptive question queue for this utterance."""
    if lu is None:
        lu = understand(text or "")
    if intent is None:
        intent = analyze_intent(text or "", lu=lu)

    skill = intent.skill_level or "beginner"
    lang = intent.language or "ar"
    primary = intent.primary.intent if intent.primary else None
    known = _known_answers(intent, lu)

    if include_optional is None:
        # experts tolerate more optional; beginners: required first only unless few required
        include_optional = skill in {"intermediate", "expert"} or (
            skill == "beginner" and len(intent.missing_slots) <= 1
        )

    candidates: list[AdaptiveQuestion] = []
    bank = _bank()

    for qid, meta in bank.items():
        slot = meta.get("slot") or qid
        intents_scope = list(meta.get("intents") or [])

        # purpose question only when no primary
        if slot == "bot_purpose" and primary:
            continue
        if slot == "bot_purpose" and not primary:
            pass
        elif intents_scope and primary and primary not in intents_scope:
            # also allow if primary None and question is bot_purpose only — handled above
            continue
        elif intents_scope and not primary:
            # without primary, only ask bot_purpose
            continue

        if _slot_filled(slot, known, intent):
            continue

        # required vs optional: skip optional when not include_optional
        # required slots are those in intent.missing_slots OR can_skip false
        can_skip = bool(meta.get("can_skip", True))
        is_required = (not can_skip) or (slot in (intent.missing_slots or []))
        if not is_required and not include_optional:
            continue
        # if we have solid primary and slot optional and beginner — skip polish questions
        if (
            can_skip
            and skill == "beginner"
            and intent.evidence_grade in {"hard", "solid"}
            and slot not in (intent.missing_slots or [])
        ):
            continue

        # wording by skill + language
        if skill == "expert":
            text_q = meta.get("expert_ar" if _is_ar(lang) else "expert_en") or meta.get(
                "ar" if _is_ar(lang) else "en"
            )
        else:
            text_q = meta.get("ar" if _is_ar(lang) else "en")
        text_q = text_q or meta.get("ar") or meta.get("en") or qid

        choices = list(meta.get("choices_ar" if _is_ar(lang) else "choices_en") or [])
        reason = "missing_required" if is_required else "optional_enrichment"
        if not primary:
            reason = "no_primary_intent"

        candidates.append(
            AdaptiveQuestion(
                id=str(meta.get("id") or qid),
                text=str(text_q),
                slot=slot,
                priority=int(meta.get("priority") or 1),
                can_skip=can_skip and not (slot in (intent.missing_slots or []) and not can_skip),
                choices=choices,
                intent_scope=intents_scope,
                reason=reason,
            )
        )

    # Priority queue: higher priority first, required before optional, stable id
    candidates.sort(key=lambda q: (-q.priority, q.can_skip, q.id))
    # Hard guarantee: no primary → bot_purpose must lead
    if not primary:
        purpose = [q for q in candidates if q.slot == "bot_purpose"]
        rest = [q for q in candidates if q.slot != "bot_purpose"]
        if not purpose and "bot_purpose" in bank:
            meta = bank["bot_purpose"]
            purpose = [
                AdaptiveQuestion(
                    id="bot_purpose",
                    text=str(meta.get("ar" if _is_ar(lang) else "en") or "What should the bot do?"),
                    slot="bot_purpose",
                    priority=10,
                    can_skip=False,
                    choices=list(meta.get("choices_ar" if _is_ar(lang) else "choices_en") or []),
                    reason="no_primary_intent",
                )
            ]
        candidates = purpose + rest
    questions = candidates[:max_questions]

    # Block generation only when critical unknowns remain
    critical_missing = [
        q for q in questions if q.slot in {"bot_purpose", "product_or_category", "payment", "security_scope"}
        or (not q.can_skip and q.reason == "missing_required")
    ]
    should_block = bool(intent.should_ask and critical_missing) or primary is None

    if _is_ar(lang):
        if not questions:
            summary = "كل التفاصيل الأساسية واضحة — جاهز للتوليد."
        elif should_block:
            summary = f"ناقص {len(questions)} توضيح(ات) قبل التوليد الدقيق."
        else:
            summary = f"ممكن نولّد الآن، وفي {len(questions)} سؤال تحسين اختياري."
    else:
        if not questions:
            summary = "Core details are clear — ready to generate."
        elif should_block:
            summary = f"{len(questions)} clarification(s) needed before precise generation."
        else:
            summary = f"Can generate now; {len(questions)} optional improvement question(s)."

    summary_en = summary if not _is_ar(lang) else (
        "Ready." if not questions else f"{len(questions)} question(s) pending."
    )
    summary_ar = summary if _is_ar(lang) else (
        "جاهز." if not questions else f"هناك {len(questions)} سؤال."
    )

    return QuestionPlan(
        questions=questions,
        answers_known=known,
        skill_level=skill,
        language=lang,
        primary_intent=primary,
        should_block_generation=should_block,
        summary_ar=summary_ar,
        summary_en=summary_en,
        intent=intent,
    )


def next_questions(text: str, *, max_questions: int = 4) -> list[dict[str, Any]]:
    plan = build_question_plan(text, max_questions=max_questions)
    return [q.to_dict() for q in plan.questions]


def apply_answer(plan: QuestionPlan, question_id: str, answer: str) -> dict[str, Any]:
    """Record an answer into known map (stateless helper for session layers)."""
    ans = (answer or "").strip()
    known = dict(plan.answers_known)
    q = next((x for x in plan.questions if x.id == question_id), None)
    if not q:
        return known
    known[q.slot] = ans
    # light interpretation
    low = ans.lower()
    if q.slot == "delivery" and any(x in low for x in ("نعم", "yes", "y", "ايوه")):
        known["delivery"] = True
    if q.slot == "discounts" and any(x in low for x in ("نعم", "yes", "y")):
        known["discounts"] = True
    if q.slot == "payment":
        mapped = []
        if any(x in low for x in ("فيزا", "visa", "card")):
            mapped.append("visa")
        if any(x in low for x in ("فودافون", "vodafone")):
            mapped.append("vodafone_cash")
        if any(x in low for x in ("فوري", "fawry")):
            mapped.append("fawry")
        if any(x in low for x in ("محفظ", "wallet")):
            mapped.append("wallet")
        if any(x in low for x in ("استلام", "cod")):
            mapped.append("cod")
        if mapped:
            known["payment"] = mapped
    return known


__all__ = [
    "AdaptiveQuestion",
    "QuestionPlan",
    "build_question_plan",
    "next_questions",
    "apply_answer",
]
