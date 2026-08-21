"""
Platform development status — single source of truth for chat models (Grok/Gemini).

When the product is updated or under active development, every chat system prompt
and SERVER_CONTEXT must carry this status so the model:

  1) Knows the platform is under continuous development.
  2) On user complaints about errors/bugs, responds honestly that the system
     is under development and issues are being fixed — without inventing excuses.
"""

from __future__ import annotations

import os
import re
from typing import Any


# ---------------------------------------------------------------------------
# Status (override via env without code change)
# ---------------------------------------------------------------------------

def is_under_development() -> bool:
    """True when the product should advertise active development."""
    raw = (os.getenv("PLATFORM_UNDER_DEVELOPMENT") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def status_label_ar() -> str:
    if is_under_development():
        return "قيد التطوير المستمر"
    return "مستقر"


def latest_update_note() -> str:
    """Optional short note about the latest update (env PLATFORM_UPDATE_NOTE)."""
    return (os.getenv("PLATFORM_UPDATE_NOTE") or "").strip()


def developer_name() -> str:
    return (os.getenv("PLATFORM_DEVELOPER_NAME") or "حاتم").strip() or "حاتم"


# ---------------------------------------------------------------------------
# Complaint detection (Arabic + English)
# ---------------------------------------------------------------------------

_COMPLAINT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(bug|error|crash|broken|fail(ed|ure)?|not\s*work)\b",
        r"(مش\s*شغال|ما\s*بيشتغلش|مبيشتغلش|بيوقع|بيخبط)",
        r"(في\s*غلط|فيه\s*غلط|في\s*خطأ|فيه\s*خطأ|فيه\s*خطا)",
        r"(مشكلة|مشكلة\s*في|عطل|خلل|باظ|بايظ)",
        r"(اشتكي|بشتكي|شكوى|مش\s*ظابط|مش\s*مظبوط)",
        r"(غلط\s*عليا|غلطت|معمول\s*غلط|شغلكم\s*وحش)",
        r"(لي\s*ه?\s*مش|ليه\s*مش|ليه\s*في)",
    )
)


def looks_like_error_complaint(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 3:
        return False
    return any(p.search(t) for p in _COMPLAINT_PATTERNS)


# ---------------------------------------------------------------------------
# User-facing reply (deterministic, when complaint detected)
# ---------------------------------------------------------------------------

def complaint_reply_ar() -> str:
    note = latest_update_note()
    base = (
        "أنت محق إن في حاجة مضايقاك — المنصة حالياً **قيد التطوير المستمر** "
        "وبنحدّثها باستمرار.\n"
        "لو حصلت أخطاء أو سلوك غريب، ده جزء من مرحلة التطوير، "
        "والمشاكل بتتصلح مع التحديثات.\n"
        "وصف المشكلة باختصار (إيه اللي حصل وإيه اللي كنت بتحاول تعمله) "
        "علشان نقدر نتابعها بشكل أدق."
    )
    if note:
        base += f"\n\nآخر ملاحظة تحديث: {note}"
    return base


# ---------------------------------------------------------------------------
# Prompt + context injection
# ---------------------------------------------------------------------------

def system_prompt_block() -> str:
    """Hard rules for the model about development status and complaints."""
    under = is_under_development()
    note = latest_update_note()
    lines = [
        "=== حالة المنصة (إلزامي) ===",
        f"- الحالة: {status_label_ar()}.",
        f"- المطور المعروف الوحيد: {developer_name()}. لا تخترع فريقاً أو شركة.",
    ]
    if under:
        lines.extend(
            [
                "- أنت (Maestro) قيد التطوير المستمر وتتطور مع كل تحديث.",
                "- إذا اشتكى المستخدم من خطأ أو عطل أو إن حاجة مش شغالة:",
                "  • اعترف بصراحة أن المنصة قيد التطوير.",
                "  • لا تدافع بأسلوب دفاعي ولا تخترع أعذاراً تقنية وهمية.",
                "  • طمّنه أن المشاكل بتتصلح مع التحديثات، واطلب وصفاً مختصراً للمشكلة إن لزم.",
                "  • جملة مناسبة: «المنصة حالياً قيد التطوير المستمر؛ لو في خطأ ظاهر وصفه باختصار وهنتابع.»",
            ]
        )
    if note:
        lines.append(f"- ملاحظة آخر تحديث: {note}")
    lines.append("=== نهاية حالة المنصة ===")
    return "\n".join(lines)


def to_context_dict() -> dict[str, Any]:
    """Inject into SERVER_CONTEXT so the model always sees platform status."""
    return {
        "platform_status": status_label_ar(),
        "platform_under_development": is_under_development(),
        "platform_update_note": latest_update_note() or None,
        "platform_developer": developer_name(),
        "platform_complaint_hint": (
            "عند شكوى المستخدم من أخطاء: أجب أن المنصة قيد التطوير المستمر "
            "وبنصلح المشاكل مع التحديثات."
            if is_under_development()
            else None
        ),
    }


__all__ = [
    "is_under_development",
    "status_label_ar",
    "latest_update_note",
    "developer_name",
    "looks_like_error_complaint",
    "complaint_reply_ar",
    "system_prompt_block",
    "to_context_dict",
]
