"""Stage-4 Smart Generation Layer — natural, personalized, adaptive responses.

Builds user-facing text for:
  • pre-generation (understanding summary)
  • in-progress status
  • post-generation delivery summary
  • adaptation notes (skill / domain / memory / learning)

Uses L6 PersonalizationStyle + Stage-1 brief + Stage-2/3 memory signals.
Zero external LLM required — compositional templates with real data slots.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .personalization_engine import PersonalizationStyle, phrase, personalize


@dataclass
class GenerationNarrative:
    """All user-facing strings for one generation turn."""
    pre_summary: str = ""
    status_start: str = ""
    status_done: str = ""
    result_header: str = ""
    result_body: str = ""
    adaptation_notes: list[str] = field(default_factory=list)
    menu_preview: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pre_summary": self.pre_summary,
            "status_start": self.status_start,
            "status_done": self.status_done,
            "result_header": self.result_header,
            "result_body": self.result_body,
            "adaptation_notes": self.adaptation_notes[:8],
            "menu_preview": self.menu_preview[:10],
        }


def _ar(style: PersonalizationStyle | None) -> bool:
    if style is None:
        return True
    return not str(getattr(style, "language_variant", "ar") or "ar").startswith("en")


def _skill(style: PersonalizationStyle | None) -> str:
    if style is None:
        return "beginner"
    s = getattr(style, "skill_level", "beginner") or "beginner"
    return s if s in {"beginner", "intermediate", "expert"} else "beginner"


def _emoji(style: PersonalizationStyle | None, fallback: str = "🤖") -> str:
    try:
        em = list(getattr(style, "emojis", None) or [])
        if em:
            return str(em[0])
    except Exception:
        pass
    return fallback


def _brief_from_entities(entities: Any) -> dict[str, Any]:
    if entities is None:
        return {}
    raw = getattr(entities, "raw", None) or {}
    if isinstance(raw, dict) and isinstance(raw.get("bot_brief"), dict):
        return raw["bot_brief"]
    return {
        "bot_name": getattr(entities, "bot_name", None),
        "purpose": getattr(entities, "bot_purpose", None),
        "features_requested": list(getattr(entities, "features_requested", None) or []),
        "action_ids": list(getattr(entities, "menu_ids", None) or []),
        "strict": bool(getattr(entities, "strict_spec", False)),
        "flows": list(getattr(entities, "flows", None) or []),
    }


_MENU_LABELS_AR = {
    "products": "🛍️ المنتجات",
    "order_track": "📦 متابعة الطلب",
    "payment_methods": "💳 طرق الدفع",
    "shipping": "🚚 الشحن",
    "support": "📞 الدعم",
    "faq": "❓ FAQ",
    "shop_catalog": "🛍️ المنتجات",
    "pay_methods": "💳 الدفع",
    "ticket_open": "📞 الدعم",
    "faq_list": "❓ الأسئلة الشائعة",
}


def _menu_preview(brief: dict, features: list[str], ar: bool) -> list[str]:
    items: list[str] = []
    actions = brief.get("action_ids") or []
    if not actions and isinstance(brief.get("menu_items"), list):
        for m in brief["menu_items"]:
            if isinstance(m, dict):
                actions.append(m.get("id") or m.get("label_ar") or "")
            else:
                actions.append(str(m))
    for a in actions[:8]:
        if ar:
            items.append(_MENU_LABELS_AR.get(str(a), f"• {a}"))
        else:
            items.append(f"• {a}")
    if not items:
        for f in features[:6]:
            if f in {"start", "help", "lang"}:
                continue
            if ar:
                items.append(_MENU_LABELS_AR.get(f, f"• {f}"))
            else:
                items.append(f"• {f}")
    return items


def build_narrative(
    request: str,
    *,
    style: PersonalizationStyle | None = None,
    entities: Any = None,
    intent_name: str | None = None,
    features: list[str] | None = None,
    learning: dict | None = None,
    memory_snap: dict | None = None,
    strict: bool | None = None,
    bot_name: str | None = None,
    success: bool | None = None,
    feature_count: int | None = None,
) -> GenerationNarrative:
    """Compose adaptive narrative for the generation lifecycle."""
    ar = _ar(style)
    skill = _skill(style)
    brief = _brief_from_entities(entities)
    name = bot_name or brief.get("bot_name") or ( "Bot" if not ar else "البوت")
    feats = list(features or brief.get("features_requested") or [])
    is_strict = strict if strict is not None else bool(brief.get("strict"))
    n = feature_count if feature_count is not None else len([f for f in feats if f not in {"start", "help", "lang"}])
    em = _emoji(style)
    nav = GenerationNarrative()
    nav.menu_preview = _menu_preview(brief, feats, ar)

    # ── Pre-summary (understanding) ──────────────────────────────
    if ar:
        if skill == "beginner":
            nav.pre_summary = (
                f"{em} تمام، هبنيلك «{name}» بشكل بسيط وواضح"
            )
        elif skill == "expert":
            nav.pre_summary = (
                f"{em} فهمت المطلوب — «{name}»"
                + (f" · intent={intent_name}" if intent_name else "")
                + (f" · strict={is_strict}" if is_strict else "")
            )
        else:
            nav.pre_summary = f"{em} جاري تجهيز «{name}» حسب وصفك"
        if nav.menu_preview:
            nav.pre_summary += "\nالقائمة:\n" + "\n".join(nav.menu_preview[:6])
        if is_strict:
            nav.pre_summary += "\n🔒 وضع صارم: الأوامر دي بس، من غير زيادة."
    else:
        nav.pre_summary = f"{em} Building «{name}» from your brief"
        if is_strict:
            nav.pre_summary += "\n🔒 Strict: only the features you listed."
        if nav.menu_preview:
            nav.pre_summary += "\nMenu:\n" + "\n".join(nav.menu_preview[:6])

    # ── Status lines ─────────────────────────────────────────────
    if ar:
        nav.status_start = {
            "beginner": f"⏳ لحظة… بجهّز «{name}»",
            "intermediate": f"⏳ توليد «{name}» ({n} ميزة)…",
            "expert": f"⏳ spec→code «{name}» n={n} strict={is_strict}",
        }.get(skill, f"⏳ جاري التوليد…")
        nav.status_done = {
            "beginner": f"✅ «{name}» جاهز!",
            "intermediate": f"✅ تم توليد «{name}» — {n} أوامر",
            "expert": f"✅ done «{name}» features={n}",
        }.get(skill, "✅ تم")
    else:
        nav.status_start = f"⏳ Generating «{name}»…"
        nav.status_done = f"✅ «{name}» ready — {n} features"

    # ── Result ───────────────────────────────────────────────────
    if success is False:
        if ar:
            nav.result_header = f"❌ فشل توليد «{name}»"
            nav.result_body = "جرّب توصف المطلوب بشكل أوضح أو اختصر القائمة."
        else:
            nav.result_header = f"❌ Failed to generate «{name}»"
            nav.result_body = "Try a clearer brief or shorter menu."
    else:
        if ar:
            nav.result_header = f"✅ «{name}» اتبنى"
            lines = [f"الأوامر/الميزات: {n}"]
            if is_strict:
                lines.append("التزمنا بوصفِك حرفيًا (بدون أوامر زيادة).")
            if nav.menu_preview:
                lines.append("القائمة:")
                lines.extend(nav.menu_preview[:6])
            nav.result_body = "\n".join(lines)
        else:
            nav.result_header = f"✅ «{name}» built"
            nav.result_body = f"Features: {n}" + (" · strict" if is_strict else "")

    # ── Adaptation notes ─────────────────────────────────────────
    notes: list[str] = []
    if skill == "beginner" and ar:
        notes.append("أسلوب مبتدئ: رسائل أوضح وأوامر أقل تعقيدًا")
    elif skill == "expert" and ar:
        notes.append("أسلوب خبير: تفاصيل تقنية أعلى")
    if is_strict and ar:
        notes.append("Strict brief مفعّل")
    if learning and isinstance(learning, dict):
        boost = learning.get("boost") or []
        avoid = learning.get("avoid") or []
        if boost and ar:
            top = ", ".join(str(x.get("feature")) for x in boost[:3] if isinstance(x, dict))
            if top:
                notes.append(f"تعلم سابق يدعم: {top}")
        if avoid and ar:
            top = ", ".join(str(x.get("feature")) for x in avoid[:2] if isinstance(x, dict))
            if top:
                notes.append(f"هنتجنب: {top}")
    if memory_snap and isinstance(memory_snap, dict):
        if memory_snap.get("corrections") and ar:
            notes.append("تصحيحاتك السابقة متطبّقة")
        if memory_snap.get("last_brief") and ar:
            notes.append("في استمرارية من آخر brief")
    nav.adaptation_notes = notes

    if notes and ar and success is not False:
        nav.result_body += "\n\n📌 " + " · ".join(notes[:4])
    elif notes and success is not False:
        nav.result_body += "\n\n📌 " + " · ".join(notes[:4])

    return nav


def status_text_for_style(
    phase: str,
    *,
    style: PersonalizationStyle | None = None,
    bot_name: str = "Bot",
    n: int = 0,
) -> str:
    """Short status string for heartbeat edits."""
    ar = _ar(style)
    skill = _skill(style)
    if phase == "start":
        return build_narrative("", style=style, bot_name=bot_name, feature_count=n).status_start
    if phase == "done":
        return build_narrative("", style=style, bot_name=bot_name, feature_count=n, success=True).status_done
    if phase == "understand":
        if ar:
            return "🧠 بفهم طلبك…" if skill != "expert" else "🧠 LU+intent…"
        return "🧠 Understanding…"
    return "…"


def format_result_addon(narrative: GenerationNarrative) -> str:
    """Extra block to append under the standard delivery message."""
    parts = []
    if narrative.result_header:
        parts.append(narrative.result_header)
    if narrative.result_body:
        parts.append(narrative.result_body)
    return "\n".join(parts).strip()


__all__ = [
    "GenerationNarrative",
    "build_narrative",
    "status_text_for_style",
    "format_result_addon",
]
