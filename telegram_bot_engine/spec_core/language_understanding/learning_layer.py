"""Stage-2 Intelligent Memory Layer — strong apply, not just store.

Episodic / semantic / procedural / corrections on SQLite MemoryEngine.
Key requirement: memory MUST change entities + feature plans + request text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .memory_engine import MemoryEngine, get_memory_engine
from .normalize import normalize_text, tokenize


@dataclass
class MemorySnapshot:
    last_brief: dict[str, Any] | None = None
    similar_briefs: list[dict[str, Any]] = field(default_factory=list)
    collective_features: list[str] = field(default_factory=list)
    corrections: list[dict[str, Any]] = field(default_factory=list)
    episodic_hints: list[str] = field(default_factory=list)
    continuity: str = ""
    applied: list[str] = field(default_factory=list)  # what memory changed this turn

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_brief": self.last_brief,
            "similar_briefs": self.similar_briefs[:5],
            "collective_features": self.collective_features[:15],
            "corrections": self.corrections[:8],
            "episodic_hints": self.episodic_hints[:5],
            "continuity": self.continuity,
            "applied": self.applied[:12],
        }


# synonym maps for applying corrections onto structured entities
_PAY_ALIASES: dict[str, list[str]] = {
    "stripe": ["stripe", "سترايب"],
    "paypal": ["paypal", "باي بال", "بايبال"],
    "vodafone_cash": ["vodafone", "فودافون", "فودافون كاش", "vf cash", "vfcash"],
    "fawry": ["fawry", "فوري"],
    "instapay": ["instapay", "انستا باي", "إنستاباي"],
    "visa": ["visa", "فيزا"],
    "mastercard": ["mastercard", "ماستركارد"],
    "cod": ["cod", "دفع عند الاستلام", "عند الاستلام"],
}

_FEATURE_ALIASES: dict[str, list[str]] = {
    "shop_catalog": ["منتجات", "كتالوج", "catalog", "products", "المتجر"],
    "order_track": ["متابعة", "تتبع", "track", "order track", "حالة الطلب"],
    "pay_methods": ["دفع", "payment", "طرق الدفع"],
    "shipping_set": ["شحن", "توصيل", "shipping", "delivery"],
    "ticket_open": ["دعم", "support", "تذكرة", "موظف"],
    "faq_list": ["faq", "أسئلة", "شائعة"],
    "wallet_balance": ["محفظة", "wallet"],
    "coupon_apply": ["كوبون", "coupon", "خصم"],
    "points_balance": ["نقاط", "points"],
    "cart_view": ["سلة", "cart"],
}


def is_correction_utterance(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    keys = (
        "لا مش", "لأ مش", "مش عايز", "مش عايزه", "غلط", "خطأ", "not that",
        "wrong", "instead", "بدل", "غير كده", "مش كده", "لا أريد", "لا اريد",
        "من غير", "بدون", "شيل", "احذف", "remove",
    )
    return any(k in t or k in low for k in keys)


def parse_correction(text: str) -> dict[str, str] | None:
    """Extract rejected → preferred. Cleaner than v1."""
    raw = (text or "").strip()
    if not raw:
        return None

    # بدل X بـ Y / بدل X عايز Y
    m = re.search(
        r"(?:بدل|instead of)\s+([^\n،,]{1,40})\s+(?:ب|بـ|with|by|عايز|أريد|I want|use)?\s*([^\n]{1,60})",
        raw,
        re.I,
    )
    if m:
        return {
            "rejected": _clean_token(m.group(1)),
            "preferred": _clean_token(m.group(2)),
        }

    # لا مش X عايز Y  |  مش عايز X عايز Y
    m = re.search(
        r"(?:لا\s*)?(?:مش|مو|not)\s*(?:عايز(?:ة)?\s+)?([A-Za-z\u0600-\u06FF][\w\u0600-\u06FF\- ]{0,40}?)"
        r"\s*(?:[,،]|و)?\s*(?:عايز(?:ة)?|أريد|want|I want)\s+([^\n]{1,60})",
        raw,
        re.I,
    )
    if m:
        rej = _clean_token(m.group(1))
        pref = _clean_token(m.group(2))
        # strip leading "عايز" leftovers
        for noise in ("عايز", "عايزة", "أريد"):
            if rej.startswith(noise):
                rej = rej[len(noise):].strip()
        return {"rejected": rej, "preferred": pref}

    # شيل X / بدون X
    m = re.search(r"(?:شيل|احذف|بدون|من غير|remove|without)\s+([^\n،,]{1,40})", raw, re.I)
    if m:
        return {"rejected": _clean_token(m.group(1)), "preferred": ""}

    if is_correction_utterance(raw):
        return {"rejected": "", "preferred": raw[:120]}
    return None


def _clean_token(s: str) -> str:
    s = (s or "").strip().strip(".,،:؛")
    for noise in ("عايز", "عايزة", "أريد", "مش", "لا"):
        if s.startswith(noise + " "):
            s = s[len(noise) + 1 :].strip()
    return s[:80]


def _match_pay(token: str) -> str | None:
    low = (token or "").lower()
    norm = normalize_text(token or "")
    for key, alts in _PAY_ALIASES.items():
        for a in alts:
            if a.lower() in low or normalize_text(a) in norm or a in (token or ""):
                return key
    return None


def _match_feature(token: str) -> str | None:
    low = (token or "").lower()
    norm = normalize_text(token or "")
    for key, alts in _FEATURE_ALIASES.items():
        for a in alts:
            if a.lower() in low or normalize_text(a) in norm or a in (token or ""):
                return key
    return None


def apply_corrections_to_entities(entities: Any, corrections: list[dict]) -> list[str]:
    """Mutate ExtractedEntities from stored/current corrections. Returns applied notes."""
    applied: list[str] = []
    if entities is None or not corrections:
        return applied

    pays = list(getattr(entities, "payment_methods", None) or [])
    feats = list(getattr(entities, "features_requested", None) or [])

    for c in corrections:
        rej = (c.get("rejected") or "").strip()
        pref = (c.get("preferred") or "").strip()

        rej_pay = _match_pay(rej) if rej else None
        pref_pay = _match_pay(pref) if pref else None
        if rej_pay and rej_pay in pays:
            pays = [p for p in pays if p != rej_pay]
            applied.append(f"-pay:{rej_pay}")
        if pref_pay and pref_pay not in pays:
            pays.append(pref_pay)
            applied.append(f"+pay:{pref_pay}")

        rej_f = _match_feature(rej) if rej else None
        pref_f = _match_feature(pref) if pref else None
        if rej_f and rej_f in feats:
            feats = [f for f in feats if f != rej_f]
            applied.append(f"-feat:{rej_f}")
        if pref_f and pref_f not in feats:
            feats.append(pref_f)
            applied.append(f"+feat:{pref_f}")

    try:
        entities.payment_methods = pays
    except Exception:
        pass
    try:
        entities.features_requested = feats
    except Exception:
        pass
    return applied


def enrich_request_with_memory(
    request: str,
    snap: MemorySnapshot,
    *,
    entities: Any = None,
) -> str:
    """Augment short/follow-up requests with last brief so generation stays consistent."""
    raw = (request or "").strip()
    if not raw:
        return raw

    # short follow-ups that mean "continue previous brief"
    follow = any(
        k in raw
        for k in (
            "نفس", "زي اللي فات", "كمل", "نفس البوت", "عدّل", "عدل", "change",
            "modify", "update the bot", "same",
        )
    )
    brief = snap.last_brief
    if not brief:
        return raw

    if follow or len(raw.split()) <= 4:
        name = brief.get("bot_name") or ""
        menu = brief.get("action_ids") or []
        if not menu and isinstance(brief.get("menu_items"), list):
            menu = [
                (m.get("id") if isinstance(m, dict) else str(m))
                for m in brief["menu_items"]
            ]
        feats = brief.get("features_requested") or []
        extra = (
            f" [ذاكرة: اسم={name} قائمة={','.join(map(str, menu[:8]))} "
            f"ميزات={','.join(map(str, feats[:10]))}]"
        )
        if extra not in raw:
            return (raw + extra).strip()
    return raw


def recall(
    user_id: int,
    request: str,
    *,
    memory: MemoryEngine | None = None,
    intent_name: str | None = None,
) -> MemorySnapshot:
    mem = memory or (get_memory_engine() if user_id else None)
    snap = MemorySnapshot()
    if mem is None or not user_id:
        return snap

    try:
        snap.last_brief = mem.last_bot_brief(int(user_id))
    except Exception:
        snap.last_brief = None

    try:
        snap.continuity = mem.continuity_hint(int(user_id)) or ""
    except Exception:
        pass

    try:
        snap.similar_briefs = mem.find_similar_briefs(request or "", limit=5)
    except Exception:
        snap.similar_briefs = []

    try:
        snap.corrections = mem.list_corrections(int(user_id), limit=15)
    except Exception:
        snap.corrections = []
    # Durable preference slots → synthetic corrections
    try:
        profile = mem.get_user(int(user_id))
        slots = dict(getattr(profile, "slots", None) or getattr(profile, "durable_slots", None) or {})
        # UserProfile may store in .data
        data = getattr(profile, "data", None) or {}
        if isinstance(data, dict):
            slots = {**slots, **{k: v for k, v in data.items() if k.startswith("preferred_") or k.startswith("rejected_")}}
        # also common API set_durable_slot
        for key in ("preferred_payment", "rejected_payment", "preferred_feature", "rejected_feature"):
            val = None
            if hasattr(profile, "get_slot"):
                try:
                    val = profile.get_slot(key)
                except Exception:
                    val = None
            if val is None and isinstance(slots, dict):
                val = slots.get(key)
            if not val:
                continue
            if key.startswith("preferred_"):
                snap.corrections.insert(0, {"rejected": "", "preferred": str(val), "context": "durable"})
            else:
                snap.corrections.insert(0, {"rejected": str(val), "preferred": "", "context": "durable"})
    except Exception:
        pass

    if intent_name:
        try:
            tops = mem.top_features_for_intent(str(intent_name), limit=12)
            # drop pure boilerplate from collective signal weight visually later
            snap.collective_features = [
                f for f, _s in tops if f not in {"start", "help", "lang"}
            ]
            # keep them available but prefer domain feats
            for f, _s in tops:
                if f not in snap.collective_features:
                    snap.collective_features.append(f)
        except Exception:
            pass

    try:
        bots = mem.list_bots(int(user_id), limit=5)
        for b in bots:
            name = b.get("name") or "bot"
            feats = b.get("features") or []
            if isinstance(feats, str):
                try:
                    import json as _json

                    feats = _json.loads(feats)
                except Exception:
                    feats = []
            snap.episodic_hints.append(
                f"{name}: {', '.join(list(feats)[:8])}" if feats else str(name)
            )
    except Exception:
        pass

    return snap


def apply_memory_to_features(
    base_features: list[str],
    snap: MemorySnapshot,
    *,
    strict: bool = False,
) -> list[str]:
    out = list(dict.fromkeys(base_features or []))
    if strict:
        # still allow correction-driven feature adds already on entities
        return out

    for f in snap.collective_features:
        if f not in out and f not in {"start", "help", "lang"}:
            out.append(f)
        if len(out) >= 22:
            break

    for sb in snap.similar_briefs[:3]:
        for f in sb.get("features") or []:
            if isinstance(f, str) and f not in out and f not in {"start", "help", "lang"}:
                out.append(f)
            if len(out) >= 26:
                break
    return out


def record_turn_learning(
    user_id: int,
    request: str,
    *,
    brief: dict | None = None,
    intent_name: str | None = None,
    features: list[str] | None = None,
    memory: MemoryEngine | None = None,
) -> None:
    if not user_id:
        return
    mem = memory or get_memory_engine()
    if brief:
        try:
            mem.store_bot_brief(int(user_id), brief, request_text=request or "")
        except Exception:
            pass
    if is_correction_utterance(request or ""):
        corr = parse_correction(request or "")
        if corr:
            try:
                mem.record_correction(
                    int(user_id),
                    rejected=corr.get("rejected") or "",
                    preferred=corr.get("preferred") or "",
                    context=request or "",
                )
            except Exception:
                pass
    if intent_name and features:
        # don't poison patterns with only boilerplate
        real = [f for f in features if f not in {"start", "help", "lang"}]
        if real:
            try:
                mem.record_patterns(intent=str(intent_name), features=list(features))
            except Exception:
                pass


def apply_full_memory(
    entities: Any,
    snap: MemorySnapshot,
    *,
    request: str = "",
) -> tuple[str, list[str]]:
    """One-shot: corrections + feature merge + request enrich. Returns (new_request, notes)."""
    notes: list[str] = []
    notes.extend(apply_corrections_to_entities(entities, snap.corrections))
    strict = bool(getattr(entities, "strict_spec", False)) if entities is not None else False
    if entities is not None:
        base = list(getattr(entities, "features_requested", None) or [])
        merged = apply_memory_to_features(base, snap, strict=strict)
        try:
            entities.features_requested = merged
        except Exception:
            pass
        if merged != base:
            notes.append(f"features:{len(base)}→{len(merged)}")
    new_req = enrich_request_with_memory(request, snap, entities=entities)
    if new_req != request:
        notes.append("request_enriched")
    snap.applied = notes
    return new_req, notes


__all__ = [
    "MemorySnapshot",
    "recall",
    "apply_memory_to_features",
    "apply_corrections_to_entities",
    "apply_full_memory",
    "enrich_request_with_memory",
    "record_turn_learning",
    "is_correction_utterance",
    "parse_correction",
]
