"""Layer 6 — Personalization Engine (zero-AI, fully dynamic).

Problem solved: generated bots used to look the same for every user.
This layer adapts *per user* using:
  • skill_level (beginner / intermediate / expert)
  • domain / intent (shop, restaurant, electronics, kids, …)
  • language variant (ar_eg / ar / en)
  • UserProfile durable prefs (complexity, naming, favorite intents)

Nothing is a final hard-coded speech. Every phrase is composed at call time
from style tokens + domain flavor + skill rules.

No external libraries — pure template / rule logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine import LanguageUnderstandingResult
from .intent_analysis import IntentAnalysis, detect_language
from .memory_engine import MemoryEngine, UserProfile, get_memory_engine


# ── Domain flavor (emojis + tone labels only; never full fixed sentences) ──
_DOMAIN_FLAVOR: dict[str, dict[str, Any]] = {
    "shop": {
        "emojis": ["🛒", "🛍️", "💳", "📦"],
        "tone": "commerce",
        "accent": "clean",
    },
    "marketplace": {
        "emojis": ["🏪", "🔍", "⭐", "📦"],
        "tone": "commerce",
        "accent": "clean",
    },
    "restaurant": {
        "emojis": ["🍕", "🍔", "🍽️", "📋"],
        "tone": "warm",
        "accent": "appetizing",
    },
    "kids": {
        "emojis": ["🧸", "🎈", "🌈", "✨"],
        "tone": "playful",
        "accent": "soft",
    },
    "electronics": {
        "emojis": ["📱", "💻", "🔌", "⚡"],
        "tone": "technical",
        "accent": "precise",
    },
    "education": {
        "emojis": ["📚", "🎓", "✅", "📝"],
        "tone": "encouraging",
        "accent": "clear",
    },
    "security": {
        "emojis": ["🔒", "🛡️", "🔍", "⚠️"],
        "tone": "professional",
        "accent": "precise",
    },
    "tickets": {
        "emojis": ["🎫", "💬", "📌", "✅"],
        "tone": "supportive",
        "accent": "clear",
    },
    "crm": {
        "emojis": ["📊", "🤝", "📈", "💼"],
        "tone": "professional",
        "accent": "clean",
    },
    "gaming": {
        "emojis": ["🎮", "🏆", "⚡", "🔥"],
        "tone": "energetic",
        "accent": "fun",
    },
    "wallet": {
        "emojis": ["💰", "💳", "📱", "✅"],
        "tone": "trust",
        "accent": "clear",
    },
    "booking": {
        "emojis": ["📅", "🗓️", "✅", "⏰"],
        "tone": "calm",
        "accent": "clear",
    },
    "default": {
        "emojis": ["🤖", "✨", "✅", "📌"],
        "tone": "neutral",
        "accent": "clean",
    },
}

# Map free-text domain hints (from entities / request) → flavor key
_DOMAIN_ALIAS: dict[str, str] = {
    "اطفال": "kids",
    "أطفال": "kids",
    "kids": "kids",
    "children": "kids",
    "العاب": "kids",
    "العاب اطفال": "kids",
    "الكترونيات": "electronics",
    "إلكترونيات": "electronics",
    "electronics": "electronics",
    "موبايل": "electronics",
    "لابتوب": "electronics",
    "tech": "electronics",
    "مطعم": "restaurant",
    "restaurant": "restaurant",
    "كافيه": "restaurant",
    "cafe": "restaurant",
    "متجر": "shop",
    "shop": "shop",
    "store": "shop",
}


@dataclass
class PersonalizationStyle:
    """Resolved style for one user + one generation request."""

    skill_level: str = "beginner"  # beginner | intermediate | expert
    domain: str = "default"
    language_variant: str = "ar"  # ar_eg | ar | en | mixed
    complexity: str = "simple"  # simple | medium | complex
    tone: str = "neutral"
    accent: str = "clean"
    emojis: list[str] = field(default_factory=lambda: ["🤖", "✨"])
    command_density: str = "few"  # few | normal | rich
    show_advanced: bool = False
    show_admin_panel: bool = False
    prefer_arabic: bool = True
    naming_style: str = "mixed"
    user_id: int | None = None
    reasons: list[str] = field(default_factory=list)

    def primary_emoji(self) -> str:
        return self.emojis[0] if self.emojis else "✨"

    def emoji_pack(self, n: int = 3) -> list[str]:
        return list(self.emojis[: max(1, n)])

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_level": self.skill_level,
            "domain": self.domain,
            "language_variant": self.language_variant,
            "complexity": self.complexity,
            "tone": self.tone,
            "accent": self.accent,
            "emojis": list(self.emojis),
            "command_density": self.command_density,
            "show_advanced": self.show_advanced,
            "show_admin_panel": self.show_admin_panel,
            "prefer_arabic": self.prefer_arabic,
            "naming_style": self.naming_style,
            "user_id": self.user_id,
            "reasons": list(self.reasons),
        }


# ── Phrase atoms (never full final sentences; composed at runtime) ──────────

_ATOMS: dict[str, dict[str, dict[str, str]]] = {
    # action keys → language_variant → skill → fragment
    "lets_add": {
        "ar_eg": {
            "beginner": "يلا نضيف",
            "intermediate": "يلا نضيف",
            "expert": "هنضيف",
        },
        "ar": {
            "beginner": "لنقم بإضافة",
            "intermediate": "سنضيف",
            "expert": "أضف",
        },
        "en": {
            "beginner": "Let's add",
            "intermediate": "We'll add",
            "expert": "Add",
        },
    },
    "welcome": {
        "ar_eg": {
            "beginner": "أهلاً بيك",
            "intermediate": "مرحباً",
            "expert": "مرحباً",
        },
        "ar": {
            "beginner": "مرحباً بك",
            "intermediate": "مرحباً",
            "expert": "أهلاً",
        },
        "en": {
            "beginner": "Welcome",
            "intermediate": "Hi",
            "expert": "Hello",
        },
    },
    "help_hint": {
        "ar_eg": {
            "beginner": "لو محتار اكتب /help",
            "intermediate": "للتفاصيل: /help",
            "expert": "/help للأوامر",
        },
        "ar": {
            "beginner": "للمساعدة اكتب /help",
            "intermediate": "التفاصيل عبر /help",
            "expert": "/help",
        },
        "en": {
            "beginner": "Type /help if you need guidance",
            "intermediate": "See /help for details",
            "expert": "/help",
        },
    },
    "success": {
        "ar_eg": {
            "beginner": "تمام، اتعمل بنجاح",
            "intermediate": "تم بنجاح",
            "expert": "تم",
        },
        "ar": {
            "beginner": "تم بنجاح",
            "intermediate": "تم",
            "expert": "✓",
        },
        "en": {
            "beginner": "Done successfully",
            "intermediate": "Done",
            "expert": "OK",
        },
    },
    "failure": {
        "ar_eg": {
            "beginner": "حصلت مشكلة، جرب تاني",
            "intermediate": "فشل — راجع المدخلات",
            "expert": "فشل",
        },
        "ar": {
            "beginner": "حدث خطأ، حاول مرة أخرى",
            "intermediate": "فشل — راجع المدخلات",
            "expert": "فشل",
        },
        "en": {
            "beginner": "Something went wrong, try again",
            "intermediate": "Failed — check inputs",
            "expert": "Failed",
        },
    },
    "simple_bot": {
        "ar_eg": {
            "beginner": "بوت بسيط وواضح",
            "intermediate": "بوت عملي",
            "expert": "بوت مضبوط",
        },
        "ar": {
            "beginner": "بوت بسيط وواضح",
            "intermediate": "بوت عملي",
            "expert": "بوت مضبوط",
        },
        "en": {
            "beginner": "a simple clear bot",
            "intermediate": "a practical bot",
            "expert": "a tight bot",
        },
    },
    "advanced_bot": {
        "ar_eg": {
            "beginner": "بوت فيه خيارات أكتر",
            "intermediate": "بوت متقدم",
            "expert": "بوت كامل (API + Admin)",
        },
        "ar": {
            "beginner": "بوت بخيارات أكثر",
            "intermediate": "بوت متقدم",
            "expert": "بوت كامل (API + Admin)",
        },
        "en": {
            "beginner": "a bot with more options",
            "intermediate": "an advanced bot",
            "expert": "full bot (API + Admin)",
        },
    },
}


def _atom(key: str, style: PersonalizationStyle) -> str:
    """Pick a phrase atom for this style (never a fixed final sentence)."""
    lang = style.language_variant if style.language_variant in {"ar_eg", "ar", "en"} else (
        "ar_eg" if style.prefer_arabic else "en"
    )
    if lang == "mixed":
        lang = "ar_eg" if style.prefer_arabic else "en"
    skill = style.skill_level if style.skill_level in {"beginner", "intermediate", "expert"} else "beginner"
    bucket = _ATOMS.get(key) or {}
    by_lang = bucket.get(lang) or bucket.get("ar") or bucket.get("en") or {}
    return by_lang.get(skill) or by_lang.get("beginner") or key


def phrase(
    key: str,
    style: PersonalizationStyle,
    *,
    subject: str = "",
    extra: str = "",
    with_emoji: bool = True,
) -> str:
    """Compose a user-facing line dynamically from atoms + style."""
    base = _atom(key, style)
    parts: list[str] = []
    if with_emoji:
        parts.append(style.primary_emoji())
    parts.append(base)
    if subject:
        parts.append(subject.strip())
    if extra:
        parts.append(extra.strip())
    return " ".join(p for p in parts if p).strip()


def _resolve_domain(
    intent: str | None,
    lu: LanguageUnderstandingResult | None,
    profile: UserProfile | None,
) -> tuple[str, list[str]]:
    """Pick domain flavor key + reasons (dynamic, not fixed)."""
    reasons: list[str] = []
    text = ""
    if lu:
        text = (lu.original or "") + " " + (lu.normalized or "")
    text_l = text.lower()

    for alias, key in _DOMAIN_ALIAS.items():
        if alias in text_l or alias in text:
            reasons.append(f"domain_alias:{alias}→{key}")
            return key, reasons

    if intent and intent in _DOMAIN_FLAVOR:
        reasons.append(f"intent:{intent}")
        return intent, reasons

    if profile and profile.favorite_intents:
        for fav in profile.favorite_intents:
            if fav in _DOMAIN_FLAVOR:
                reasons.append(f"favorite_intent:{fav}")
                return fav, reasons

    if lu and lu.primary_domain and lu.primary_domain in _DOMAIN_FLAVOR:
        reasons.append(f"lu_domain:{lu.primary_domain}")
        return lu.primary_domain, reasons

    reasons.append("fallback:default")
    return "default", reasons


def _resolve_language(
    intent: IntentAnalysis | None,
    lu: LanguageUnderstandingResult | None,
    profile: UserProfile | None,
    text: str = "",
) -> str:
    if intent and intent.language:
        return intent.language
    if profile and profile.language_preference in {"ar", "ar_eg", "en", "mixed"}:
        return profile.language_preference
    if text:
        return detect_language(text)
    if lu and getattr(lu, "original", None):
        return detect_language(lu.original)
    return "ar"


def _resolve_skill(
    intent: IntentAnalysis | None,
    profile: UserProfile | None,
) -> str:
    order = {"beginner": 0, "intermediate": 1, "expert": 2}
    skill = "beginner"
    if intent and intent.skill_level:
        skill = intent.skill_level
    if profile and profile.skill_level:
        if order.get(profile.skill_level, 0) > order.get(skill, 0):
            skill = profile.skill_level
        elif profile.total_builds >= 5 and skill == "beginner":
            skill = "intermediate"
    return skill if skill in order else "beginner"


def build_personalization(
    *,
    text: str = "",
    intent: IntentAnalysis | None = None,
    lu: LanguageUnderstandingResult | None = None,
    user_id: int | None = None,
    profile: UserProfile | None = None,
    memory: MemoryEngine | None = None,
) -> PersonalizationStyle:
    """Main entry: resolve a full PersonalizationStyle for this request."""
    reasons: list[str] = []

    if profile is None and user_id is not None:
        try:
            mem = memory or get_memory_engine()
            profile = mem.get_user(int(user_id))
        except Exception:
            profile = None

    primary = None
    if intent and intent.primary:
        primary = intent.primary.intent
    elif lu:
        primary = lu.primary_domain

    domain, dom_reasons = _resolve_domain(primary, lu, profile)
    reasons.extend(dom_reasons)

    flavor = _DOMAIN_FLAVOR.get(domain) or _DOMAIN_FLAVOR["default"]
    lang = _resolve_language(intent, lu, profile, text)
    skill = _resolve_skill(intent, profile)

    complexity = "simple"
    if intent and intent.complexity:
        complexity = intent.complexity
    elif lu and lu.complexity_hint:
        complexity = lu.complexity_hint
    if profile and profile.complexity_preference in {"simple", "medium", "complex"}:
        order_c = {"simple": 0, "medium": 1, "complex": 2}
        if order_c.get(profile.complexity_preference, 0) > order_c.get(complexity, 0):
            complexity = profile.complexity_preference
            reasons.append(f"profile_complexity:{complexity}")

    if skill == "expert":
        density, advanced, admin = "rich", True, True
    elif skill == "intermediate":
        density, advanced, admin = "normal", True, False
    else:
        density, advanced, admin = "few", False, False

    if domain in {"electronics", "security", "crm"} and skill != "beginner":
        density = "rich" if density != "few" else "normal"
        advanced = True
        reasons.append(f"domain_nudge:{domain}")

    prefer_ar = lang in {"ar", "ar_eg", "mixed"}
    naming = profile.naming_style if profile else "mixed"

    return PersonalizationStyle(
        skill_level=skill,
        domain=domain,
        language_variant=lang,
        complexity=complexity,
        tone=str(flavor.get("tone") or "neutral"),
        accent=str(flavor.get("accent") or "clean"),
        emojis=list(flavor.get("emojis") or ["🤖", "✨"]),
        command_density=density,
        show_advanced=advanced,
        show_admin_panel=admin,
        prefer_arabic=prefer_ar,
        naming_style=naming,
        user_id=user_id,
        reasons=reasons,
    )


def feature_filter_for_skill(
    features: list[str],
    style: PersonalizationStyle,
) -> list[str]:
    """Reduce / keep features according to command density (core features stay)."""
    if style.command_density == "rich" or style.skill_level == "expert":
        return list(features)

    advanced = {
        "coupon_create",
        "admin_panel",
        "api_endpoint",
        "webhook_set",
        "analytics_view",
        "bulk_import",
        "role_manage",
        "sec_headers_check",
        "pipeline_board",
        "wallet_topup",
    }
    if style.command_density == "few":
        return [f for f in features if f not in advanced]
    heavy = {"bulk_import", "role_manage", "webhook_set"}
    return [f for f in features if f not in heavy]


def adapt_message(
    base: str,
    style: PersonalizationStyle,
    *,
    kind: str = "success",
) -> str:
    """Adapt an existing message string to the user's style without replacing meaning."""
    base = (base or "").strip()
    if not base:
        return phrase(kind if kind in _ATOMS else "success", style)

    emoji = style.primary_emoji()
    if style.skill_level == "beginner":
        if emoji and emoji not in base:
            return f"{emoji} {base}"
        return base
    if style.skill_level == "intermediate":
        if emoji and not base.startswith(emoji):
            return f"{emoji} {base}"
        return base
    if len(base) > 40 and kind in _ATOMS:
        return phrase(kind, style, with_emoji=True)
    if emoji and emoji not in base:
        return f"{emoji} {base}"
    return base


def style_prompt_ar(style: PersonalizationStyle) -> str:
    """Human-readable summary (Arabic) of the active personalization — dynamic."""
    skill_ar = {
        "beginner": "مبتدئ → أوامر قليلة ورسائل واضحة",
        "intermediate": "متوسط → توازن بين الوضوح والخيارات",
        "expert": "محترف → أوامر غنية + خيارات متقدمة/Admin",
    }.get(style.skill_level, style.skill_level)
    lang_ar = {
        "ar_eg": "عربي مصري",
        "ar": "عربي فصحى",
        "en": "English",
        "mixed": "مختلط",
    }.get(style.language_variant, style.language_variant)
    domain_ar = {
        "kids": "متجر أطفال",
        "electronics": "إلكترونيات",
        "restaurant": "مطعم",
        "shop": "متجر",
        "security": "أمن",
        "education": "تعليم",
    }.get(style.domain, style.domain)
    em = " ".join(style.emoji_pack(3))
    return (
        f"التخصيص الحالي:\n"
        f"• المستوى: {skill_ar}\n"
        f"• المجال: {domain_ar} {em}\n"
        f"• اللغة: {lang_ar}\n"
        f"• كثافة الأوامر: {style.command_density}\n"
        f"• متقدم/Admin: {'نعم' if style.show_advanced else 'لا'}"
        f"{' / نعم' if style.show_admin_panel else ' / لا'}"
    )


def style_prompt_en(style: PersonalizationStyle) -> str:
    skill_en = {
        "beginner": "beginner → few commands, clear messages",
        "intermediate": "intermediate → balanced",
        "expert": "expert → rich commands + advanced/Admin",
    }.get(style.skill_level, style.skill_level)
    em = " ".join(style.emoji_pack(3))
    return (
        f"Active personalization:\n"
        f"• Skill: {skill_en}\n"
        f"• Domain: {style.domain} {em}\n"
        f"• Language: {style.language_variant}\n"
        f"• Command density: {style.command_density}\n"
        f"• Advanced/Admin: {style.show_advanced}/{style.show_admin_panel}"
    )


def personalize(
    text: str = "",
    *,
    intent: IntentAnalysis | None = None,
    lu: LanguageUnderstandingResult | None = None,
    user_id: int | None = None,
    memory: MemoryEngine | None = None,
) -> PersonalizationStyle:
    """Public convenience entry (mirrors suggest() style)."""
    return build_personalization(
        text=text,
        intent=intent,
        lu=lu,
        user_id=user_id,
        memory=memory,
    )


__all__ = [
    "PersonalizationStyle",
    "build_personalization",
    "personalize",
    "phrase",
    "feature_filter_for_skill",
    "adapt_message",
    "style_prompt_ar",
    "style_prompt_en",
]
