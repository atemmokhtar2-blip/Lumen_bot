"""Language Understanding Engine — Layer 1 foundation (zero-AI).

Understands Arabic/English bot requests beyond fixed keywords:
  synonyms, fuzzy typos, entity extraction, ambiguity detection.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .entities import ExtractedEntities, extract_entities
from .fuzzy import best_match, partial_ratio
from .normalize import normalize_text, tokenize

_DATA = Path(__file__).resolve().parent / "data"

# domain → preset key used by the rest of the system
DOMAIN_TO_PRESET: dict[str, str] = {
    "shop": "shop",
    "marketplace": "marketplace",
    "restaurant": "restaurant",
    "booking": "booking",
    "tickets": "support_pro",
    "wallet": "wallet",
    "payments": "shop",
    "delivery": "shop",
    "education": "education",
    "crm": "crm",
    "saas": "saas",
    "security": "security_ops",
    "iot": "iot",
    "tasks": "tasks",
    "notes": "notes",
    "growth": "growth",
    "points": "points",
    "subscriptions": "subscriptions",
    "contests": "contests",
    "jobs": "jobs",
    "events": "events",
    "fitness": "fitness",
    "clinic": "clinic",
    "commerce_pro": "commerce_pro",
}


@dataclass
class DomainSignal:
    domain: str
    score: float
    confidence: float
    sources: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)


@dataclass
class LanguageUnderstandingResult:
    original: str
    normalized: str
    tokens: list[str]
    domains: list[DomainSignal]
    primary_domain: str | None
    primary_preset: str | None
    entities: ExtractedEntities
    is_ambiguous: bool
    ambiguity_reason: str
    skill_hint: str  # beginner | intermediate | expert
    suggested_questions: list[str] = field(default_factory=list)
    feature_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized": self.normalized,
            "primary_domain": self.primary_domain,
            "primary_preset": self.primary_preset,
            "domains": [
                {"domain": d.domain, "score": d.score, "confidence": d.confidence, "matched": d.matched}
                for d in self.domains[:8]
            ],
            "entities": self.entities.to_dict(),
            "is_ambiguous": self.is_ambiguous,
            "ambiguity_reason": self.ambiguity_reason,
            "skill_hint": self.skill_hint,
            "suggested_questions": self.suggested_questions,
            "feature_hints": self.feature_hints,
        }


@lru_cache(maxsize=1)
def _load_json(name: str) -> dict:
    path = _DATA / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _stop_words() -> set[str]:
    path = _DATA / "stop_words_ar.txt"
    if not path.exists():
        return set()
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()}


def _all_synonym_entries() -> dict[str, list[str]]:
    ar = _load_json("synonyms_ar.json")
    en = _load_json("synonyms_en.json")
    merged: dict[str, list[str]] = {}
    for src in (ar, en):
        for dom, words in src.items():
            merged.setdefault(dom, [])
            for w in words:
                nw = normalize_text(w)
                if nw and nw not in merged[dom]:
                    merged[dom].append(nw)
    return merged


def _content_tokens(text: str) -> list[str]:
    stops = _stop_words()
    return [t for t in tokenize(text) if t not in stops and len(t) > 1]


def _skill_hint(text: str, tokens: list[str]) -> str:
    tech = {
        "api", "webhook", "rest", "oauth", "sqlite", "postgres", "docker",
        "microservice", "rate limit", "jwt", "ci/cd", "kubernetes",
        "webhook", "endpoint", "schema", "middleware",
    }
    low = (text or "").lower()
    hits = sum(1 for t in tech if t in low)
    if hits >= 2 or len(tokens) > 25:
        return "expert"
    if hits == 1 or len(tokens) > 12:
        return "intermediate"
    return "beginner"


def _feature_hints(entities: ExtractedEntities, domains: list[DomainSignal]) -> list[str]:
    hints: list[str] = []
    doms = {d.domain for d in domains}
    if "shop" in doms or "marketplace" in doms:
        hints += ["shop_catalog", "cart_view", "cart_checkout", "shop_add_item"]
        if entities.wants_discounts:
            hints += ["coupon_apply", "coupon_create"]
        if entities.wants_delivery:
            hints += ["shipping_set", "order_track"]
        if entities.wants_wallet or "vodafone_cash" in entities.payment_methods:
            hints += ["wallet_balance", "wallet_topup", "vodafone_cash", "pay_methods"]
        if "visa" in entities.payment_methods or "telegram_payments" in entities.payment_methods:
            hints += ["shop_buy", "payment_history", "pay_methods"]
        if entities.payment_methods and "pay_methods" not in hints:
            hints.append("pay_methods")
    if "tickets" in doms:
        hints += ["ticket_open", "ticket_my", "ticket_list"]
    if "booking" in doms:
        hints += ["table_book", "order_status"] if "restaurant" in doms else ["job_list"]
    if "subscriptions" in doms:
        hints += ["plans", "subscribe", "my_sub"]
    if "points" in doms:
        hints += ["balance", "leaderboard"]
    # unique preserve order
    out: list[str] = []
    for h in hints:
        if h not in out:
            out.append(h)
    return out


def _suggested_questions(result_partial: dict[str, Any]) -> list[str]:
    """Adaptive questions only for missing critical slots."""
    qs: list[str] = []
    primary = result_partial.get("primary_domain")
    ent: ExtractedEntities = result_partial.get("entities") or ExtractedEntities()
    if not primary:
        qs.append("عايز البوت يعمل إيه بالظبط؟ (متجر / دعم / حجوزات / تعليم…)")
        return qs
    if primary in {"shop", "marketplace"}:
        if not ent.product:
            qs.append("هتبيع إيه في المتجر؟ (مثال: ملابس أطفال / إلكترونيات)")
        if not ent.payment_methods:
            qs.append("طرق الدفع؟ (فيزا / فودافون كاش / محفظة / عند الاستلام)")
        if not ent.wants_delivery:
            qs.append("محتاج توصيل وتتبع شحنات؟")
        if not ent.wants_discounts:
            qs.append("عايز كوبونات وخصومات؟")
    elif primary == "tickets":
        qs.append("التذاكر للإدارة الداخلية ولا لعملاء خارجيين؟")
    elif primary == "booking":
        qs.append("الحجز لمواعيد / طاولات / خدمات؟")
    return qs[:4]


def understand(text: str) -> LanguageUnderstandingResult:
    original = text or ""
    normalized = normalize_text(original)
    tokens = _content_tokens(original)
    synonyms = _all_synonym_entries()

    # Build reverse index: normalized synonym → domain
    rev: dict[str, set[str]] = {}
    all_syn_list: list[str] = []
    for dom, words in synonyms.items():
        if dom == "bot":
            continue
        for w in words:
            rev.setdefault(w, set()).add(dom)
            all_syn_list.append(w)

    scores: dict[str, DomainSignal] = {}

    def _bump(dom: str, amount: float, source: str, matched: str) -> None:
        if dom not in scores:
            scores[dom] = DomainSignal(domain=dom, score=0.0, confidence=0.0, sources=[], matched=[])
        s = scores[dom]
        s.score += amount
        if source not in s.sources:
            s.sources.append(source)
        if matched and matched not in s.matched:
            s.matched.append(matched)

    # 1) exact token / phrase hits
    for tok in tokens:
        if tok in rev:
            for dom in rev[tok]:
                _bump(dom, 2.2, "keyword", tok)
        else:
            # fuzzy against synonyms
            m, sc = best_match(tok, all_syn_list, cutoff=75.0)
            if m and m in rev:
                for dom in rev[m]:
                    _bump(dom, 2.0 * (sc / 100.0) + 0.5, "fuzzy", f"{tok}~{m}")

    # 2) multi-word phrase partial match on normalized full text
    for dom, words in synonyms.items():
        if dom == "bot":
            continue
        for w in words:
            if len(w) >= 4 and w in normalized:
                _bump(dom, 2.5, "phrase", w)
            elif len(w) >= 5:
                pr = partial_ratio(w, normalized)
                if pr >= 88:
                    _bump(dom, 1.2, "partial", w)

    # 3) intent keyword boosts
    intent_kw = _load_json("intent_keywords.json")
    for dom, groups in intent_kw.items():
        for w in groups.get("primary") or []:
            if normalize_text(w) in normalized:
                _bump(dom, 2.0, "intent_primary", w)
        for w in groups.get("secondary") or []:
            if normalize_text(w) in normalized:
                _bump(dom, 1.0, "intent_secondary", w)

    # Rank domains
    # Sell / commerce verbs strongly prefer shop over pure delivery
    sell_signals = any(
        x in normalized
        for x in ("يبيع", "بيع", "لبيع", "منتج", "منتجات", "متجر", "محل", "shop", "store", "catalog", "cart")
    )
    if sell_signals and "shop" in scores:
        scores["shop"].score += 2.0
        if "delivery" in scores and scores["delivery"].score <= scores["shop"].score + 1:
            scores["delivery"].score *= 0.6

    ranked = sorted(scores.values(), key=lambda d: d.score, reverse=True)
    for d in ranked:
        # confidence: squash score
        d.confidence = max(0.0, min(0.99, d.score / (d.score + 4.0)))

    primary = ranked[0].domain if ranked and ranked[0].score >= 1.0 else None
    primary_preset = DOMAIN_TO_PRESET.get(primary) if primary else None

    entities = extract_entities(original)

    # Ambiguity: no domain OR top two very close OR only "bot" with no domain
    is_ambiguous = False
    reason = ""
    if not primary:
        is_ambiguous = True
        reason = "لم يتضح نوع البوت من النص"
    elif len(ranked) >= 2 and abs(ranked[0].score - ranked[1].score) < 0.8 and ranked[1].score >= 1.5:
        is_ambiguous = True
        reason = f"تعارض بين {ranked[0].domain} و {ranked[1].domain}"
    elif len(tokens) <= 2 and primary and ranked[0].confidence < 0.55:
        is_ambiguous = True
        reason = "الوصف قصير جداً — نحتاج تفاصيل"

    skill = _skill_hint(original, tokens)
    feature_hints = _feature_hints(entities, ranked)

    partial = {"primary_domain": primary, "entities": entities}
    questions = _suggested_questions(partial) if is_ambiguous or (
        primary in {"shop", "marketplace"} and not entities.product
    ) else []

    return LanguageUnderstandingResult(
        original=original,
        normalized=normalized,
        tokens=tokens,
        domains=ranked,
        primary_domain=primary,
        primary_preset=primary_preset,
        entities=entities,
        is_ambiguous=is_ambiguous,
        ambiguity_reason=reason,
        skill_hint=skill,
        suggested_questions=questions,
        feature_hints=feature_hints,
    )


__all__ = [
    "LanguageUnderstandingResult",
    "DomainSignal",
    "understand",
    "DOMAIN_TO_PRESET",
]
