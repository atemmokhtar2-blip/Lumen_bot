"""Data models for Capability Detection Engine (Phase 1).

Deterministic only — no web, no LLM. Answers:
  EXISTS | COMPOSABLE | GAP | IMPOSSIBLE
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DetectionStatus(str, Enum):
    """High-level outcome of capability detection."""

    EXISTS = "exists"  # all requested features map to known registry keys
    COMPOSABLE = "composable"  # can assemble from multiple known capabilities
    GAP = "gap"  # some features missing; registry has partial coverage
    IMPOSSIBLE = "impossible"  # feasibility gate blocked the request


@dataclass(frozen=True)
class MatchedCapability:
    key: str
    service: str
    method: str
    category: str
    description_ar: str
    description_en: str
    score: float = 1.0  # 0..1 match strength
    source: str = "extractor"  # extractor | search | domain | core


@dataclass
class GapItem:
    """A requested concept that has no direct registry key."""

    phrase: str
    reason: str
    suggested_keys: list[str] = field(default_factory=list)
    suggested_categories: list[str] = field(default_factory=list)


@dataclass
class DetectionReport:
    """Full result of capability detection for one user request."""

    status: DetectionStatus
    request: str
    matched: list[MatchedCapability] = field(default_factory=list)
    gaps: list[GapItem] = field(default_factory=list)
    categories_covered: list[str] = field(default_factory=list)
    confidence: float = 0.0
    can_generate: bool = True
    reason_ar: str = ""
    reason_en: str = ""
    suggested_scope_ar: str = ""
    feasibility_level: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def matched_keys(self) -> list[str]:
        return [m.key for m in self.matched]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "request": self.request[:500],
            "matched_keys": self.matched_keys(),
            "matched": [
                {
                    "key": m.key,
                    "service": m.service,
                    "method": m.method,
                    "category": m.category,
                    "score": round(m.score, 3),
                    "source": m.source,
                }
                for m in self.matched
            ],
            "gaps": [
                {
                    "phrase": g.phrase,
                    "reason": g.reason,
                    "suggested_keys": g.suggested_keys[:8],
                    "suggested_categories": g.suggested_categories[:5],
                }
                for g in self.gaps
            ],
            "categories_covered": self.categories_covered,
            "confidence": round(self.confidence, 3),
            "can_generate": self.can_generate,
            "reason_ar": self.reason_ar,
            "reason_en": self.reason_en,
            "suggested_scope_ar": self.suggested_scope_ar,
            "feasibility_level": self.feasibility_level,
            "metadata": dict(self.metadata or {}),
        }

    def human_report_ar(self) -> str:
        """Fail-safe transparent report for the user (Arabic)."""
        lines: list[str] = []
        status_label = {
            DetectionStatus.EXISTS: "✅ كل الميزات المطلوبة موجودة في القوالب",
            DetectionStatus.COMPOSABLE: "🔧 يمكن تركيب البوت من أدوات موجودة",
            DetectionStatus.GAP: "⚠️ جزء من الطلب غير مغطى بالكامل في القوالب الحالية",
            DetectionStatus.IMPOSSIBLE: "🚫 الطلب خارج قدرات المحرك الحتمي",
        }
        lines.append(status_label.get(self.status, self.status.value))
        lines.append("")
        if self.reason_ar:
            lines.append(f"السبب: {self.reason_ar}")
        if self.matched:
            lines.append("")
            lines.append(f"الميزات المطابقة ({len(self.matched)}):")
            for m in self.matched[:12]:
                lines.append(f"  • {m.key} — {m.description_ar}")
            if len(self.matched) > 12:
                lines.append(f"  … و{len(self.matched) - 12} أخرى")
        if self.gaps:
            lines.append("")
            lines.append("فجوات (غير موجودة مباشرة):")
            for g in self.gaps[:8]:
                lines.append(f"  • «{g.phrase}» — {g.reason}")
                if g.suggested_keys:
                    lines.append(f"    أقرب: {', '.join(g.suggested_keys[:4])}")
        if self.suggested_scope_ar:
            lines.append("")
            lines.append(f"💡 نطاق مقترح: {self.suggested_scope_ar}")
        return "\n".join(lines)


__all__ = [
    "DetectionStatus",
    "MatchedCapability",
    "GapItem",
    "DetectionReport",
]
