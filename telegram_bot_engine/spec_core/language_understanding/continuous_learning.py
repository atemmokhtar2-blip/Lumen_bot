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


def feature_weights(
    intent: str | None,
    *,
    memory: MemoryEngine | None = None,
    user_id: int | None = None,
) -> dict[str, float]:
    """Positive weights from success recipes, negative from avoids."""
    mem = memory or get_memory_engine()
    weights: dict[str, float] = {}
    if intent:
        for rec in top_recipes(intent, memory=mem, limit=5):
            for i, f in enumerate(rec.features):
                weights[f] = weights.get(f, 0.0) + float(rec.weight) * (1.0 / (1 + i * 0.05))
        try:
            for f, s in mem.top_features_for_intent(str(intent), limit=15):
                if f in {"start", "help", "lang"}:
                    continue
                weights[f] = weights.get(f, 0.0) + float(s)
        except Exception:
            pass
    # Global avoid list from pattern_avoid events (+ user-specific)
    try:
        with mem._conn() as conn:
            rows = conn.execute(
                "SELECT user_id, payload_json FROM event_log WHERE event=? ORDER BY id DESC LIMIT 150",
                ("pattern_avoid",),
            ).fetchall()
        for r in rows:
            try:
                data = json.loads(r["payload_json"] or "{}")
            except Exception:
                continue
            # prefer user-specific avoids
            boost = 1.0 if user_id and r["user_id"] == int(user_id) else 0.4
            if intent and data.get("intent") and data["intent"] != intent:
                continue
            for f in data.get("features") or []:
                if isinstance(f, str):
                    # soft decay — single negative must not erase success recipes
                    weights[f] = weights.get(f, 0.0) - 0.7 * boost
    except Exception:
        pass
    return weights


def apply_success_learning(
    base_features: list[str],
    intent: str | None,
    *,
    strict: bool = False,
    memory: MemoryEngine | None = None,
    user_id: int | None = None,
    max_extra: int = 8,
) -> list[str]:
    """Rank + merge + drop avoided features.

    strict: never ADD features, but still DROP features with strong negative weight
            (so bad extras learned from failures get removed).
    """
    out = list(dict.fromkeys(base_features or []))
    weights = feature_weights(intent, memory=memory, user_id=user_id)

    # Drop strongly avoided features (even under strict) except core
    core = {"start", "help", "lang"}
    dropped = []
    kept = []
    for f in out:
        if f not in core and weights.get(f, 0.0) <= -1.6:
            dropped.append(f)
            continue
        kept.append(f)
    out = kept

    if strict or not intent:
        return out

    # Add high-weight success features not already present
    ranked = sorted(
        ((f, w) for f, w in weights.items() if w > 0.4 and f not in core),
        key=lambda x: -x[1],
    )
    added = 0
    for f, _w in ranked:
        if f in out:
            continue
        out.append(f)
        added += 1
        if added >= max_extra:
            break

    # Re-rank: core first, then by weight desc
    def sort_key(f: str) -> tuple:
        if f in core:
            return (0, -10.0, f)
        return (1, -float(weights.get(f, 0.0)), f)

    out = list(dict.fromkeys(sorted(out, key=sort_key)))
    return out


def learn_from_feedback_message(
    user_id: int,
    text: str,
    *,
    bot_id: str | None = None,
    memory: MemoryEngine | None = None,
) -> OutcomeSignal:
    """Feedback after generation — ties to LAST bot features for real learning."""
    sig = detect_outcome(text)
    if not user_id:
        return sig
    mem = memory or get_memory_engine()
    rating = 5 if sig.score_delta >= 5 else (1 if sig.score_delta < 0 else 3)

    last = None
    try:
        last = mem.last_bot(int(user_id))
    except Exception:
        last = None
    last_feats: list[str] = []
    last_intent = ""
    if last:
        bot_id = bot_id or str(last.get("bot_id") or last.get("name") or "")
        last_intent = str(last.get("intent") or "")
        feats = last.get("features") or []
        if isinstance(feats, str):
            try:
                feats = json.loads(feats)
            except Exception:
                feats = []
        last_feats = [str(f) for f in feats if f]

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

    # Reinforce or avoid the exact feature set of the last bot
    if last_feats:
        if sig.score_delta > 0:
            try:
                for _ in range(2):
                    mem.record_patterns(
                        intent=last_intent or "general",
                        features=last_feats,
                    )
                mem._event(
                    int(user_id),
                    "success_recipe",
                    {
                        "intent": last_intent or "general",
                        "purpose": last_intent or "",
                        "features": last_feats[:24],
                        "bot_name": (last or {}).get("name"),
                        "request": ((last or {}).get("request_text") or "")[:200],
                        "from_feedback": True,
                    },
                )
            except Exception:
                pass
        elif sig.score_delta < 0:
            try:
                # Soft-avoid experimental extras only (not core commerce/support verbs)
                protect = {
                    "start", "help", "lang", "shop_catalog", "order_track",
                    "pay_methods", "ticket_open", "faq_list", "product_info",
                }
                avoid_feats = [f for f in last_feats if f not in protect][:24]
                if not avoid_feats:
                    # if only core features, mark mild avoid on nothing — just rating
                    avoid_feats = []
                if avoid_feats:
                    mem._event(
                        int(user_id),
                        "pattern_avoid",
                        {
                            "intent": last_intent or "general",
                            "features": avoid_feats,
                            "reason": text[:120],
                        },
                    )
                mem._event(
                    int(user_id),
                    "bot_failed",
                    {
                        "intent": last_intent or "general",
                        "bot": (last or {}).get("name"),
                        "features": last_feats[:20],
                        "reason": text[:120],
                    },
                )
            except Exception:
                pass

    return learn_from_interaction(
        int(user_id),
        text,
        intent=last_intent or None,
        features=last_feats or None,
        memory=mem,
    )


def learning_summary(
    user_id: int | None,
    intent: str | None,
    *,
    memory: MemoryEngine | None = None,
) -> dict[str, Any]:
    """Explain what Stage-3 knows — for meta / user transparency."""
    mem = memory or get_memory_engine()
    weights = feature_weights(intent, memory=mem, user_id=user_id)
    top_pos = sorted(((f, w) for f, w in weights.items() if w > 0), key=lambda x: -x[1])[:8]
    top_neg = sorted(((f, w) for f, w in weights.items() if w < 0), key=lambda x: x[1])[:6]
    score = 0
    if user_id:
        try:
            profile = mem.get_user(int(user_id))
            data = dict(getattr(profile, "data", None) or {})
            score = int(data.get("learning_score", 0) or 0)
        except Exception:
            pass
    return {
        "user_score": score,
        "boost": [{"feature": f, "w": round(w, 2)} for f, w in top_pos],
        "avoid": [{"feature": f, "w": round(w, 2)} for f, w in top_neg],
        "recipes": [r.to_dict() for r in top_recipes(intent or "general", memory=mem, limit=3)],
    }


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
    "feature_weights",
    "learning_summary",
    "is_feedback_only",
]
