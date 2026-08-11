"""Stage-2 Intelligent Memory Layer — episodic + semantic + corrections.

Built on SQLite MemoryEngine (no external vector DB required yet).
- Episodic: interaction ledger + bot briefs
- Semantic: feature co-occurrence patterns + similar briefs (token overlap)
- Procedural: successful generation recipes (features that worked together)
- Corrections: user said "not X, Y" → stored and applied next time
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .memory_engine import MemoryEngine, get_memory_engine
from .normalize import normalize_text, tokenize


@dataclass
class MemorySnapshot:
    """What Stage-2 recalls for this user + request."""
    last_brief: dict[str, Any] | None = None
    similar_briefs: list[dict[str, Any]] = field(default_factory=list)
    collective_features: list[str] = field(default_factory=list)
    corrections: list[dict[str, Any]] = field(default_factory=list)
    episodic_hints: list[str] = field(default_factory=list)
    continuity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_brief": self.last_brief,
            "similar_briefs": self.similar_briefs[:5],
            "collective_features": self.collective_features[:15],
            "corrections": self.corrections[:8],
            "episodic_hints": self.episodic_hints[:5],
            "continuity": self.continuity,
        }


_CORRECTION_PATTERNS = [
    re.compile(
        r"(?:لا|لأ|مش|مو|not|no)[^\n]{0,40}?(?:عايز|أريد|أريد|want|I want)?\s*([^\n]{2,80})",
        re.I,
    ),
    re.compile(
        r"(?:غلط|خطأ|wrong|incorrect)[^\n]{0,20}?(?:[:]|=)?\s*([^\n]{2,80})",
        re.I,
    ),
    re.compile(
        r"(?:بدل|instead of|rather than)\s+([^\n،,]{2,40})\s+(?:عايز|أريد|I want)?\s*([^\n]{2,40})",
        re.I,
    ),
]


def is_correction_utterance(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    keys = (
        "لا مش", "لأ مش", "مش عايز", "غلط", "خطأ", "not that", "wrong",
        "instead", "بدل", "غير كده", "مش كده", "لا أريد",
    )
    return any(k in t or k in low for k in keys)


def parse_correction(text: str) -> dict[str, str] | None:
    """Extract rejected → preferred from a correction utterance."""
    raw = (text or "").strip()
    if not raw:
        return None
    # بدل X عايز Y
    m = re.search(
        r"(?:بدل|instead of)\s+([^\n،,]{2,40})\s+(?:عايز|أريد|I want|use)?\s*([^\n]{2,40})",
        raw,
        re.I,
    )
    if m:
        return {"rejected": m.group(1).strip()[:80], "preferred": m.group(2).strip()[:80]}
    # لا مش Stripe عايز فودافون
    m = re.search(
        r"(?:لا|لأ|مش|not)\s+(?:عايز\s+)?([A-Za-z\u0600-\u06FF][\w\u0600-\u06FF\s]{1,40})\s*"
        r"(?:[,،]?)\s*(?:عايز|أريد|want|I want)\s+([^\n]{2,60})",
        raw,
        re.I,
    )
    if m:
        return {"rejected": m.group(1).strip()[:80], "preferred": m.group(2).strip()[:80]}
    # generic: keep whole text as preferred signal
    if is_correction_utterance(raw):
        return {"rejected": "", "preferred": raw[:120]}
    return None


def _token_set(text: str) -> set[str]:
    return {t for t in tokenize(normalize_text(text or "")) if len(t) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def recall(
    user_id: int,
    request: str,
    *,
    memory: MemoryEngine | None = None,
    intent_name: str | None = None,
) -> MemorySnapshot:
    """Build Stage-2 memory snapshot for this turn."""
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
        snap.corrections = mem.list_corrections(int(user_id), limit=10)
    except Exception:
        snap.corrections = []

    # Collective procedural knowledge: top features for this intent across users
    if intent_name:
        try:
            tops = mem.top_features_for_intent(str(intent_name), limit=10)
            snap.collective_features = [f for f, _ in tops]
        except Exception:
            pass

    # Episodic: last few successful bots
    try:
        bots = mem.list_bots(int(user_id), limit=3)
        for b in bots:
            name = b.get("name") or "bot"
            feats = b.get("features") or []
            if isinstance(feats, str):
                feats = []
            snap.episodic_hints.append(
                f"{name}: {', '.join(list(feats)[:6])}" if feats else str(name)
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
    """Merge memory knowledge into feature list.

    Strict mode: never add collective extras — only honor brief + corrections.
    """
    out = list(dict.fromkeys(base_features or []))
    if strict:
        return out

    # soft boost from collective success patterns
    for f in snap.collective_features:
        if f not in out:
            out.append(f)
        if len(out) >= 24:
            break

    # similar briefs' features (weak signal)
    for sb in snap.similar_briefs[:3]:
        for f in sb.get("features") or []:
            if isinstance(f, str) and f not in out:
                out.append(f)
            if len(out) >= 28:
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
    """Persist Stage-2 signals for this turn."""
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
        try:
            mem.record_patterns(intent=str(intent_name), features=list(features))
        except Exception:
            pass


__all__ = [
    "MemorySnapshot",
    "recall",
    "apply_memory_to_features",
    "record_turn_learning",
    "is_correction_utterance",
    "parse_correction",
]
