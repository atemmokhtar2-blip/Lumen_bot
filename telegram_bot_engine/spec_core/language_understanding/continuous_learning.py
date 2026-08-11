"""Stage-3 Continuous Learning Layer.

Learns from:
  A) Interactions — every turn scored
  B) Corrections — already in Stage-2, reinforced here with weights
  C) Success — recipes from bots that completed successfully

No external ML required: weighted SQLite patterns + recipe store.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .memory_engine import MemoryEngine, get_memory_engine
from .normalize import normalize_text


# ── Interaction outcome signals ─────────────────────────────────────────────
_POSITIVE = (
    "تمام", "تمامًا", "تماما", "شكرا", "شكرًا", "thanks", "thank you",
    "ممتاز", "حلو", "كويس", "صح", "صح كده", "ok", "okay", "perfect", "great",
    "اشتغل", "شغال", "نجح", "good", "awesome", "👍", "✅",
)
_NEGATIVE = (
    "غلط", "خطأ", "مش شغال", "مش تمام", "وحش", "فاشل", "broken", "wrong",
    "error", "fail", "مش كده", "مش عايز كده", "سيء", "bad", "❌", "💔",
)
_COMPLETE = (
    "خلص", "انتهى", "جاهز", "done", "finished", "complete", "published",
    "نشر", "ارفع", "deploy",
)


@dataclass
class OutcomeSignal:
    kind: str  # positive | negative | complete | neutral
    score_delta: int
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "score_delta": self.score_delta, "raw": self.raw[:80]}


@dataclass
class SuccessRecipe:
    """Features that co-occurred in successful bots for an intent/purpose."""
    intent: str
    features: list[str] = field(default_factory=list)
    weight: float = 1.0
    samples: int = 1
    purpose: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "purpose": self.purpose,
            "features": self.features[:24],
            "weight": round(self.weight, 3),
            "samples": self.samples,
        }


def detect_outcome(text: str) -> OutcomeSignal:
    t = (text or "").strip()
    low = t.lower()
    norm = normalize_text(t)

    def _hit(keys: tuple[str, ...]) -> bool:
        for k in keys:
            if not k:
                continue
            if len(k) <= 2:
                # short keys: whole-word only
                if low == k or t == k:
                    return True
                continue
            if k in t or k in low or normalize_text(k) in norm:
                return True
        return False

    # Negation first so «مش شغال» is not counted positive via «شغال»
    if _hit(_NEGATIVE):
        return OutcomeSignal("negative", -5, t)
    if _hit(_COMPLETE):
        return OutcomeSignal("complete", +10, t)
    if _hit(_POSITIVE):
        return OutcomeSignal("positive", +5, t)
    return OutcomeSignal("neutral", 0, t)


def learn_from_interaction(
    user_id: int,
    text: str,
    *,
    intent: str | None = None,
    features: list[str] | None = None,
    memory: MemoryEngine | None = None,
) -> OutcomeSignal:
    """Score the turn and persist. Reinforces or weakens patterns."""
    sig = detect_outcome(text)
    if not user_id:
        return sig
    mem = memory or get_memory_engine()
    try:
        mem._event(
            int(user_id),
            "interaction_outcome",
            {
                "kind": sig.kind,
                "delta": sig.score_delta,
                "intent": intent,
                "features": list(features or [])[:20],
                "text": (text or "")[:200],
            },
        )
    except Exception:
        pass

    # Reinforce / decay feature patterns for this intent
    if intent and features and sig.score_delta != 0:
        try:
            if sig.score_delta > 0:
                mem.record_patterns(intent=str(intent), features=list(features))
            # negative: record under intent__avoid soft key once
            elif sig.score_delta < 0:
                mem._event(
                    int(user_id),
                    "pattern_avoid",
                    {"intent": intent, "features": list(features)[:20]},
                )
        except Exception:
            pass

    # user score slot
    try:
        profile = mem.get_user(int(user_id))
        data = dict(getattr(profile, "data", None) or {})
        score = int(data.get("learning_score", 0) or 0) + int(sig.score_delta)
        data["learning_score"] = score
        data["last_outcome"] = sig.kind
        # UserProfile save
        if hasattr(profile, "data"):
            profile.data = data  # type: ignore
        mem.save_user(profile)
    except Exception:
        pass

    return sig


def learn_from_success(
    user_id: int,
    *,
    intent: str,
    features: list[str],
    purpose: str = "",
    bot_name: str = "",
    request_text: str = "",
    memory: MemoryEngine | None = None,
) -> SuccessRecipe:
    """Called after a successful bot build — store recipe + boost patterns."""
    mem = memory or get_memory_engine()
    real_feats = [f for f in (features or []) if f not in {"start", "help", "lang"}]
    recipe = SuccessRecipe(
        intent=str(intent or "general"),
        features=real_feats,
        weight=1.0,
        samples=1,
        purpose=purpose or "",
    )
    try:
        mem._event(
            int(user_id) if user_id else None,
            "success_recipe",
            {
                "intent": recipe.intent,
                "purpose": recipe.purpose,
                "features": recipe.features[:24],
                "bot_name": bot_name,
                "request": (request_text or "")[:300],
            },
        )
    except Exception:
        pass

    if recipe.intent and recipe.features:
        try:
            # triple-weight success patterns vs normal turns
            for _ in range(3):
                mem.record_patterns(intent=recipe.intent, features=list(features or []))
        except Exception:
            pass

    # index brief-like recipe for similarity
    try:
        if user_id:
            mem.store_bot_brief(
                int(user_id),
                {
                    "bot_name": bot_name,
                    "purpose": purpose or recipe.intent,
                    "features_requested": list(features or [])[:30],
                    "action_ids": real_feats[:15],
                    "strict": False,
                    "from_success": True,
                },
                request_text=request_text or "",
            )
    except Exception:
        pass

    return recipe


def top_recipes(
    intent: str,
    *,
    memory: MemoryEngine | None = None,
    limit: int = 5,
) -> list[SuccessRecipe]:
    """Aggregate success_recipe events + pattern co-occurrence into recipes."""
    mem = memory or get_memory_engine()
    buckets: dict[str, SuccessRecipe] = {}
    try:
        with mem._conn() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM event_log WHERE event=? ORDER BY id DESC LIMIT 200",
                ("success_recipe",),
            ).fetchall()
        for r in rows:
            try:
                data = json.loads(r["payload_json"] or "{}")
            except Exception:
                continue
            if intent and data.get("intent") and data["intent"] != intent:
                # still allow same purpose soft match
                if data.get("purpose") != intent:
                    continue
            key = data.get("intent") or "general"
            feats = [f for f in (data.get("features") or []) if isinstance(f, str)]
            if key not in buckets:
                buckets[key] = SuccessRecipe(
                    intent=key,
                    features=list(feats),
                    weight=1.0,
                    samples=1,
                    purpose=str(data.get("purpose") or ""),
                )
            else:
                b = buckets[key]
                b.samples += 1
                b.weight += 1.0
                for f in feats:
                    if f not in b.features:
                        b.features.append(f)
    except Exception:
        pass

    # merge pattern tops
    try:
        tops = mem.top_features_for_intent(intent, limit=12)
        if tops:
            key = intent or "general"
            feats = [f for f, _ in tops if f not in {"start", "help", "lang"}]
            if key not in buckets:
                buckets[key] = SuccessRecipe(intent=key, features=feats, weight=0.5, samples=1)
            else:
                for f in feats:
                    if f not in buckets[key].features:
                        buckets[key].features.append(f)
                buckets[key].weight += 0.5
    except Exception:
        pass

    recipes = sorted(buckets.values(), key=lambda r: -r.weight)
    return recipes[:limit]


def apply_success_learning(
    base_features: list[str],
    intent: str | None,
    *,
    strict: bool = False,
    memory: MemoryEngine | None = None,
    max_extra: int = 6,
) -> list[str]:
    """Merge success recipes into feature plan (never under strict)."""
    out = list(dict.fromkeys(base_features or []))
    if strict or not intent:
        return out
    recipes = top_recipes(intent, memory=memory, limit=3)
    added = 0
    for rec in recipes:
        for f in rec.features:
            if f in out or f in {"start", "help", "lang"}:
                continue
            out.append(f)
            added += 1
            if added >= max_extra:
                return out
    return out


def learn_from_feedback_message(
    user_id: int,
    text: str,
    *,
    bot_id: str | None = None,
    memory: MemoryEngine | None = None,
) -> OutcomeSignal:
    """Explicit feedback after generation (تمام / مش شغال)."""
    sig = detect_outcome(text)
    if not user_id:
        return sig
    mem = memory or get_memory_engine()
    rating = 5 if sig.score_delta >= 5 else (1 if sig.score_delta < 0 else 3)
    try:
        mem.record_feedback(
            int(user_id),
            bot_id=bot_id or "",
            rating=rating,
            liked=text if sig.score_delta > 0 else "",
            disliked=text if sig.score_delta < 0 else "",
        )
    except Exception:
        pass
    return learn_from_interaction(
        int(user_id),
        text,
        memory=mem,
    )


def is_feedback_only(text: str) -> bool:
    """True when message is pure feedback, not a new bot request."""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    sig = detect_outcome(t)
    if sig.kind == "neutral":
        return False
    # has bot-building intent words? then not feedback-only
    if any(k in t.lower() or k in t for k in ("بوت", "bot", "اعمل", "سوي", "سوّي", "generate", "ضيف")):
        return False
    return True


__all__ = [
    "OutcomeSignal",
    "SuccessRecipe",
    "detect_outcome",
    "learn_from_interaction",
    "learn_from_success",
    "learn_from_feedback_message",
    "top_recipes",
    "apply_success_learning",
    "is_feedback_only",
]
