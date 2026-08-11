"""Capability Detection Engine — Phase 1.

Pipeline (deterministic, zero-AI):
  1. Feasibility gate (impossible / complex external APIs)
  2. Existing capability_extractor (exact keyword → real keys only)
  3. Registry search for residual phrases
  4. Classify: EXISTS | COMPOSABLE | GAP | IMPOSSIBLE
  5. Build human Fail-Safe report

Does NOT call the web and does NOT invent capabilities outside CAPABILITIES.
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
from .search import nearest_keys_for_phrase, search_capabilities, tokenize

# Phrases that often signal composition of known domains (not a true gap)
_COMPOSITION_HINTS = (
    "مع",
    "و",
    "plus",
    "with",
    "and",
    "دمج",
    "معاً",
    "مع بعض",
    "كامل",
    "متكامل",
)

# Residual concept patterns that are NOT covered by extractor keywords well
_GAP_CANDIDATE_RE = re.compile(
    r"(ترجم|ترجمة|translate|translation|"
    r"صورة|صور|image|vision|ocr|"
    r"صوت|voice|speech|tts|stt|"
    r"ذكاء|ai\b|gpt|llm|"
    r"بلوكتشين|blockchain|nft|"
    r"تعدين|mining|"
    r"اختراق|hack|"
    r"فيديو\s*حي|live\s*video|voip|"
    r"stripe|paypal|payment\s*gateway)",
    re.I,
)


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


def _merge_matched(
    primary: list[MatchedCapability],
    extra: list[MatchedCapability],
) -> list[MatchedCapability]:
    seen: set[str] = set()
    out: list[MatchedCapability] = []
    for m in primary + extra:
        if m.key in seen:
            continue
        seen.add(m.key)
        out.append(m)
    # stable: higher score first, then key
    out.sort(key=lambda m: (-m.score, m.key))
    return out


def _detect_gap_phrases(request: str, matched_keys: set[str]) -> list[GapItem]:
    """Heuristic residual phrases not explained by matched capabilities."""
    text = (request or "").strip()
    if not text:
        return []

    gaps: list[GapItem] = []
    # Known hard gaps from pattern list
    for m in _GAP_CANDIDATE_RE.finditer(text):
        phrase = m.group(0).strip()
        # Skip if already covered by a matched key that mentions similar concept
        covered = False
        low = phrase.lower()
        for k in matched_keys:
            if low in k or any(p in k for p in low.split() if len(p) > 3):
                covered = True
                break
        # lang capability covers "ترجمة" as UI language only — still flag auto-translate intent
        if low in {"ترجم", "ترجمة", "translate", "translation"}:
            if "lang" in matched_keys and not re.search(
                r"ترجم(ة)?\s*(ال)?رسائل|auto\s*translat|ترجم\s*تلقائ", text, re.I
            ):
                # UI language change — not a gap
                continue
            nearest = nearest_keys_for_phrase(phrase, limit=4)
            gaps.append(
                GapItem(
                    phrase=phrase,
                    reason="الترجمة التلقائية للرسائل غير موجودة كقدرة تنفيذية (lang = لغة الواجهة فقط)",
                    suggested_keys=nearest or ["lang"],
                    suggested_categories=["i18n"],
                )
            )
            continue
        if covered:
            continue
        nearest = nearest_keys_for_phrase(phrase, limit=5)
        cats = []
        for nk in nearest:
            c = get_capability(nk)
            if c and c.category not in cats:
                cats.append(c.category)
        gaps.append(
            GapItem(
                phrase=phrase,
                reason="لا يوجد مفتاح مطابق مباشرة في سجل القدرات",
                suggested_keys=nearest,
                suggested_categories=cats,
            )
        )

    # De-dupe by phrase
    seen: set[str] = set()
    unique: list[GapItem] = []
    for g in gaps:
        p = g.phrase.lower()
        if p in seen:
            continue
        seen.add(p)
        unique.append(g)
    return unique


def _classify(
    *,
    feas: FeasibilityResult,
    matched: list[MatchedCapability],
    gaps: list[GapItem],
    request: str,
) -> tuple[DetectionStatus, float, str, str, str]:
    """Return status, confidence, reason_ar, reason_en, suggested_scope_ar."""
    if not feas.can_generate or feas.level == ComplexityLevel.IMPOSSIBLE:
        return (
            DetectionStatus.IMPOSSIBLE,
            float(feas.confidence),
            feas.reason or "الطلب خارج النطاق",
            "Request outside deterministic engine scope",
            feas.suggested_scope or "اطلب بوت أوامر/متجر/تذاكر داخل تيليجرام",
        )

    if gaps and not matched:
        return (
            DetectionStatus.GAP,
            max(0.35, float(feas.confidence) - 0.2),
            "الميزات المطلوبة غير موجودة في سجل القدرات الحالي",
            "Requested features are not in the current capability registry",
            feas.suggested_scope
            or "جرّب وصفاً يعتمد على أوامر، متجر، نقاط، تذاكر، ترحيب، أو اشتراكات",
        )

    if gaps and matched:
        return (
            DetectionStatus.GAP,
            max(0.45, float(feas.confidence) - 0.1),
            f"جزء من الطلب مغطى ({len(matched)} قدرة)؛ توجد فجوات: "
            + "، ".join(g.phrase for g in gaps[:4]),
            f"Partial coverage ({len(matched)} caps); gaps remain",
            "يمكن توليد الجزء المدعوم؛ الفجوات تُستبعد أو تُستبدل بأقرب قدرات",
        )

    # No gaps
    if len(matched) <= 2 and not any(h in (request or "") for h in _COMPOSITION_HINTS):
        # single-feature style
        return (
            DetectionStatus.EXISTS,
            min(0.95, float(feas.confidence) + 0.05),
            f"الميزات المطلوبة موجودة مباشرة ({len(matched)} قدرة)",
            f"Requested features map directly to registry ({len(matched)} caps)",
            "",
        )

    # Multiple known caps → composable
    return (
        DetectionStatus.COMPOSABLE,
        min(0.92, float(feas.confidence) + 0.05),
        f"يمكن تركيب البوت من {len(matched)} قدرة موجودة في السجل",
        f"Bot can be assembled from {len(matched)} known capabilities",
        "",
    )


def detect_capabilities(
    request: str,
    *,
    domains: Iterable[str] | None = None,
    search_limit: int = 15,
    include_search: bool = True,
) -> DetectionReport:
    """Main entry — detect what the registry can already satisfy.

    Parameters
    ----------
    request:
        Free-text user description (Arabic/English).
    domains:
        Optional domain hints from domain_detector (passed through to extractor).
    search_limit:
        Max extra keys from registry search.
    include_search:
        If False, only use capability_extractor (stricter).
    """
    text = (request or "").strip()
    feas = check_feasibility(text)

    # 1) Exact extractor keys (never invents)
    extracted_keys = extract_all(text, domains=domains)
    matched: list[MatchedCapability] = []
    for k in extracted_keys:
        m = _to_matched(k, score=1.0, source="extractor")
        if m:
            matched.append(m)

    # Always ensure core if anything matched
    if matched:
        for core in ("start", "help"):
            if core not in {m.key for m in matched}:
                cm = _to_matched(core, score=0.9, source="core")
                if cm:
                    matched.append(cm)

    # 2) Soft search for additional related keys (still registry-only)
    # Prefer extractor; search only fills modest extras and avoids scale noise.
    if include_search and text and feas.can_generate:
        already = {m.key for m in matched}
        preferred_cats = {m.category for m in matched if m.source == "extractor"}
        min_s = 0.35 if matched else 0.25
        extra_limit = min(search_limit, 6 if matched else 10)
        for cap, score in search_capabilities(text, limit=max(extra_limit * 3, 15), min_score=min_s):
            if cap.key in already:
                continue
            # When extractor already hit, only accept same-category or strong scores
            if preferred_cats and cap.category not in preferred_cats and score < 0.55:
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
            if len([m for m in matched if m.source == "search"]) >= extra_limit:
                break

    matched = _merge_matched(matched, [])

    # 3) Gaps (only when generation is not already impossible)
    gaps: list[GapItem] = []
    if feas.can_generate:
        gaps = _detect_gap_phrases(text, {m.key for m in matched})

    # Feasibility blocked features become gaps too
    for bf in feas.blocked_features or []:
        if not any(bf.lower() in (g.phrase.lower()) for g in gaps):
            gaps.append(
                GapItem(
                    phrase=bf,
                    reason="محظور أو يحتاج تكامل خارجي غير متوفر في المسار الحتمي",
                    suggested_keys=[],
                    suggested_categories=[],
                )
            )

    status, confidence, reason_ar, reason_en, scope_ar = _classify(
        feas=feas, matched=matched, gaps=gaps, request=text
    )

    cats = sorted({m.category for m in matched})
    can_gen = bool(feas.can_generate) and status != DetectionStatus.IMPOSSIBLE
    # GAP still allows partial generation of matched parts
    if status == DetectionStatus.GAP and matched:
        can_gen = True

    meta = {
        "extracted_count": len(extracted_keys),
        "search_enabled": include_search,
        "registry_size": len(CAPABILITIES),
        "feasibility": {
            "can_generate": feas.can_generate,
            "level": feas.level.value if hasattr(feas.level, "value") else str(feas.level),
            "confidence": feas.confidence,
        },
        "tokens": tokenize(text)[:24],
    }

    return DetectionReport(
        status=status,
        request=text,
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
    """Convenience: status only."""
    return detect_capabilities(request).status


def can_satisfy(request: str) -> bool:
    """True when EXISTS or COMPOSABLE (full coverage, no gaps)."""
    rep = detect_capabilities(request)
    return rep.status in (DetectionStatus.EXISTS, DetectionStatus.COMPOSABLE)


__all__ = [
    "detect_capabilities",
    "detect_status",
    "can_satisfy",
]
