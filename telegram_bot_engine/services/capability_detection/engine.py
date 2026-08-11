"""Capability Detection Engine — Phase 1 (hardened).

Pipeline (deterministic, zero-AI):
  1. Feasibility gate
  2. Domain detector (hints for extractor)
  3. capability_extractor (exact keyword → real keys only)
  4. Primary-only registry search for residual coverage
  5. Gap analysis
  6. Classify: EXISTS | COMPOSABLE | GAP | IMPOSSIBLE

Never invents keys outside CAPABILITIES. Never calls the web.
"""
from __future__ import annotations

import re
from typing import Iterable

from ...spec_core.capability_extractor import extract_all
from ...spec_core.registry import CAPABILITIES, get_capability
from ..feasibility_gate import ComplexityLevel, FeasibilityResult, check_feasibility
from .models import (
    DetectionReport,
    DetectionStatus,
    GapItem,
    MatchedCapability,
)
from .normalize import expand_for_match, normalize_ar, strip_negations
from .search import nearest_keys_for_phrase, search_capabilities, tokenize

_COMPOSITION_HINTS = (
    "مع", "و", "plus", "with", "and", "دمج", "معاً", "مع بعض", "كامل", "متكامل",
)

# Residual concepts that are commonly requested but not executable as full features
_GAP_SPECS: list[tuple[re.Pattern[str], str, list[str], list[str]]] = [
    (
        re.compile(r"ترجم(ة)?\s*(ال)?رسائل|auto\s*translat|ترجم\s*تلقائ|يترجم", re.I),
        "الترجمة التلقائية للرسائل غير موجودة كقدرة تنفيذية (lang = لغة الواجهة فقط)",
        ["lang"],
        ["i18n"],
    ),
    (
        re.compile(r"تحليل\s*صور|تعرف\s*على\s*الصور|image\s*recog|ocr|وصف\s*الصور|vision\s*api", re.I),
        "تحليل/وصف الصور يحتاج نماذج خارجية غير متوفرة في المسار الحتمي",
        [],
        [],
    ),
    (
        re.compile(r"\b(gpt|llm|chatgpt|openai)\b|ذكاء\s*اصطناعي\s*(حقيقي|توليدي)|يتعلم\s*من", re.I),
        "نماذج الذكاء الاصطناعي التوليدي خارج نطاق التوليد الحتمي",
        [],
        [],
    ),
    (
        re.compile(r"stripe|paypal|payment\s*gateway|بوابة\s*دفع", re.I),
        "بوابة دفع خارجية تحتاج مفاتيح API غير مضمّنة",
        ["shop_buy", "payment_success"],
        ["payments", "shop"],
    ),
    (
        re.compile(r"صوت|voice\s*note|speech|tts|stt|تحويل\s*صوت", re.I),
        "معالجة الصوت/الكلام غير مدعومة كقدرة تنفيذية حالياً",
        [],
        [],
    ),
    (
        re.compile(r"فيديو\s*حي|live\s*video|voip|مكالمة\s*فيديو", re.I),
        "الفيديو الحي/VoIP خارج نطاق بوتات الأوامر",
        [],
        [],
    ),
]


def _to_matched(key: str, score: float = 1.0, source: str = "extractor") -> MatchedCapability | None:
    cap = get_capability(key)
    if not cap:
        return None
    return MatchedCapability(
        key=cap.key,
        service=cap.service,
        method=cap.method,
        category=cap.category,
        description_ar=cap.description_ar,
        description_en=cap.description_en,
        score=float(score),
        source=source,
    )


def _merge_matched(items: list[MatchedCapability]) -> list[MatchedCapability]:
    seen: set[str] = set()
    out: list[MatchedCapability] = []
    for m in items:
        if m.key in seen:
            continue
        seen.add(m.key)
        out.append(m)
    out.sort(key=lambda m: (-m.score, m.key))
    return out


def _detect_gaps(request: str, matched_keys: set[str]) -> list[GapItem]:
    text = (request or "").strip()
    if not text:
        return []
    gaps: list[GapItem] = []
    for pat, reason, suggested, cats in _GAP_SPECS:
        if not pat.search(text):
            continue
        # skip if already covered by a real matched key that is not merely "lang" for translate
        if "ترجم" in reason or "translat" in reason.lower():
            # lang alone does not cover auto-translate
            pass
        elif suggested and any(s in matched_keys for s in suggested):
            continue
        m = pat.search(text)
        phrase = (m.group(0) if m else pat.pattern)[:48]
        nearest = list(suggested) if suggested else nearest_keys_for_phrase(phrase, limit=4)
        gaps.append(
            GapItem(
                phrase=phrase,
                reason=reason,
                suggested_keys=nearest[:6],
                suggested_categories=list(cats),
            )
        )
    # de-dupe by reason
    seen: set[str] = set()
    unique: list[GapItem] = []
    for g in gaps:
        if g.reason in seen:
            continue
        seen.add(g.reason)
        unique.append(g)
    return unique


def _classify(
    *,
    feas: FeasibilityResult,
    matched: list[MatchedCapability],
    gaps: list[GapItem],
    request: str,
) -> tuple[DetectionStatus, float, str, str, str]:
    if not feas.can_generate or feas.level == ComplexityLevel.IMPOSSIBLE:
        return (
            DetectionStatus.IMPOSSIBLE,
            float(feas.confidence),
            feas.reason or "الطلب خارج النطاق",
            "Request outside deterministic engine scope",
            feas.suggested_scope or "اطلب بوت أوامر/متجر/تذاكر داخل تيليجرام",
        )

    n = len(matched)

    if n == 0 and gaps:
        return (
            DetectionStatus.GAP,
            max(0.35, float(feas.confidence) - 0.25),
            "الميزات المطلوبة غير موجودة في سجل القدرات الحالي",
            "Requested features are not in the current capability registry",
            feas.suggested_scope
            or "جرّب وصفاً يعتمد على أوامر، متجر، نقاط، تذاكر، ترحيب، مسابقات، أو اشتراكات",
        )

    if n == 0:
        # Nothing matched and no structured gap — still a soft gap
        return (
            DetectionStatus.GAP,
            max(0.40, float(feas.confidence) - 0.2),
            "لم يُعثر على قدرات مطابقة بوضوح في السجل",
            "No clear capability matches in the registry",
            "اذكر أوامر أو ميزات محددة مثل ترحيب، متجر، تذاكر، نقاط، مسابقات",
        )

    if gaps:
        return (
            DetectionStatus.GAP,
            max(0.50, float(feas.confidence) - 0.1),
            f"جزء من الطلب مغطى ({n} قدرة)؛ توجد فجوات",
            f"Partial coverage ({n} caps); gaps remain",
            "يمكن توليد الجزء المدعوم؛ الفجوات تُستبعد أو تُستبدل بأقرب قدرات",
        )

    # Full coverage
    multi = n >= 3 or any(h in (request or "") for h in _COMPOSITION_HINTS)
    if multi:
        return (
            DetectionStatus.COMPOSABLE,
            min(0.95, float(feas.confidence) + 0.08),
            f"يمكن تركيب البوت من {n} قدرة موجودة في السجل",
            f"Bot can be assembled from {n} known capabilities",
            "",
        )
    return (
        DetectionStatus.EXISTS,
        min(0.96, float(feas.confidence) + 0.08),
        f"الميزات المطلوبة موجودة مباشرة ({n} قدرة)",
        f"Requested features map directly to registry ({n} caps)",
        "",
    )


def _resolve_domains(request: str, domains: Iterable[str] | None) -> list[str]:
    if domains:
        return [d for d in domains if d]
    try:
        from ...spec_core.domain_detector import detect

        return list(detect(request) or [])
    except Exception:
        return []


def detect_capabilities(
    request: str,
    *,
    domains: Iterable[str] | None = None,
    search_limit: int = 10,
    include_search: bool = True,
) -> DetectionReport:
    """Main entry — detect what the registry can already satisfy."""
    original = (request or "").strip()
    text = original
    # Dialect/synonym expansion for matching only
    match_text = expand_for_match(strip_negations(original)) if original else ""
    feas = check_feasibility(original)
    resolved_domains = _resolve_domains(match_text or original, domains)

    # Phase 4: load capability packs (overlay registry + keyword index)
    try:
        from .packs import ensure_packs_loaded, keyword_hits
        ensure_packs_loaded()
        _pack_hits = keyword_hits(match_text or original)
    except Exception:
        _pack_hits = []

    # 1) Exact extractor keys (never invents) — run on expanded match text
    extracted_keys = extract_all(match_text or original, domains=resolved_domains or None)
    for _pk in _pack_hits:
        if _pk not in extracted_keys:
            extracted_keys.append(_pk)
    matched: list[MatchedCapability] = []
    from .search import is_bulk_key
    for k in extracted_keys:
        m = _to_matched(k, score=1.0, source="extractor")
        if not m:
            continue
        # Domain packs sometimes inject scale-like keys; drop bulk noise
        if is_bulk_key(m.key, m.category) and m.key not in {
            "shop_catalog", "cart_view", "balance", "leaderboard", "plans",
        }:
            continue
        matched.append(m)

    if matched:
        for core in ("start", "help"):
            if core not in {m.key for m in matched}:
                cm = _to_matched(core, score=0.9, source="core")
                if cm:
                    matched.append(cm)

    # Early structured gaps (translate/vision/LLM...) — avoid noisy soft-search
    early_gaps = _detect_gaps(original, {m.key for m in matched})
    hard_gap = bool(early_gaps) and not any(
        m.key not in {"start", "help", "lang"} for m in matched
    )

    # 2) Primary-only soft search (skip when hard external gap dominates)
    #    - If extractor already found real feature keys: only same-category, high score
    #    - If extractor empty: broader primary search
    if include_search and text and feas.can_generate and not hard_gap:
        already = {m.key for m in matched}
        feature_matched = [m for m in matched if m.source == "extractor" and m.key not in {"start", "help"}]
        preferred_cats = {m.category for m in feature_matched}

        if feature_matched:
            min_s = 0.40
            extra_limit = min(search_limit, 5)
            hits = search_capabilities(
                match_text or text, limit=extra_limit * 2, min_score=min_s, primary_only=True
            )
            added = 0
            for cap, score in hits:
                if cap.key in already:
                    continue
                if preferred_cats and cap.category not in preferred_cats and score < 0.60:
                    continue
                matched.append(
                    MatchedCapability(
                        key=cap.key,
                        service=cap.service,
                        method=cap.method,
                        category=cap.category,
                        description_ar=cap.description_ar,
                        description_en=cap.description_en,
                        score=float(score),
                        source="search",
                    )
                )
                already.add(cap.key)
                added += 1
                if added >= extra_limit:
                    break
        else:
            hits = search_capabilities(
                match_text or text, limit=search_limit, min_score=0.32, primary_only=True
            )
            for cap, score in hits:
                if cap.key in already:
                    continue
                matched.append(
                    MatchedCapability(
                        key=cap.key,
                        service=cap.service,
                        method=cap.method,
                        category=cap.category,
                        description_ar=cap.description_ar,
                        description_en=cap.description_en,
                        score=float(score),
                        source="search",
                    )
                )
                already.add(cap.key)

    matched = _merge_matched(matched)

    # 3) Gaps
    gaps: list[GapItem] = []
    if feas.can_generate or feas.level != ComplexityLevel.IMPOSSIBLE:
        gaps = _detect_gaps(original, {m.key for m in matched})

    for bf in feas.blocked_features or []:
        if not any(bf.lower() in (g.reason.lower() + g.phrase.lower()) for g in gaps):
            gaps.append(
                GapItem(
                    phrase=bf,
                    reason="محظور أو يحتاج تكامل خارجي غير متوفر في المسار الحتمي",
                    suggested_keys=[],
                    suggested_categories=[],
                )
            )

    status, confidence, reason_ar, reason_en, scope_ar = _classify(
        feas=feas, matched=matched, gaps=gaps, request=original
    )

    cats = sorted({m.category for m in matched})
    can_gen = bool(feas.can_generate) and status != DetectionStatus.IMPOSSIBLE
    if status == DetectionStatus.GAP and matched:
        can_gen = True

    meta = {
        "extracted_count": len(extracted_keys),
        "search_enabled": include_search,
        "registry_size": len(CAPABILITIES),
        "domains": resolved_domains,
        "feasibility": {
            "can_generate": feas.can_generate,
            "level": feas.level.value if hasattr(feas.level, "value") else str(feas.level),
            "confidence": feas.confidence,
        },
        "tokens": tokenize(match_text or original)[:24],
        "feature_keys": [m.key for m in matched if m.key not in {"start", "help"}],
    }

    return DetectionReport(
        status=status,
        request=original,
        matched=matched,
        gaps=gaps,
        categories_covered=cats,
        confidence=confidence,
        can_generate=can_gen,
        reason_ar=reason_ar,
        reason_en=reason_en,
        suggested_scope_ar=scope_ar or feas.suggested_scope or "",
        feasibility_level=feas.level.value if hasattr(feas.level, "value") else str(feas.level),
        metadata=meta,
    )


def detect_status(request: str) -> DetectionStatus:
    return detect_capabilities(request).status


def can_satisfy(request: str) -> bool:
    rep = detect_capabilities(request)
    return rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE) and not rep.gaps


__all__ = [
    "detect_capabilities",
    "detect_status",
    "can_satisfy",
]
