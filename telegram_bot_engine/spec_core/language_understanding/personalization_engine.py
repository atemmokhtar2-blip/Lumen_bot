"""Layer 6 — Personalization Engine (zero-AI, fully dynamic, L5-aware).

Problem solved: generated bots + suggestion prompts looked the same for everyone.

Adapts *per user* using:
  • skill_level (beginner / intermediate / expert)
  • domain / intent (shop, restaurant, electronics, kids, …)
  • language variant (ar_eg / ar / en)
  • UserProfile durable prefs (complexity, preferred_features, favorite_intents)

Nothing is a final hard-coded speech. Every phrase / label / reason is composed
at call time from style tokens + domain flavor + skill rules.

Deep L5 integration:
  • personalize_suggestions() — rewrite labels, reasons, confidence, order
  • domain affinity boosts for features
  • skill filters which suggestion kinds appear
  • profile preferred_features get priority

No external libraries — pure template / rule logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine import LanguageUnderstandingResult
from .intent_analysis import IntentAnalysis, detect_language
from .memory_engine import MemoryEngine, UserProfile, get_memory_engine


# ── Domain flavor ───────────────────────────────────────────────────────────
_DOMAIN_FLAVOR: dict[str, dict[str, Any]] = {
    "shop": {
        "emojis": ["🛒", "🛍️", "💳", "📦"],
        "tone": "commerce",
        "accent": "clean",
        "boost": ["cart_view", "cart_checkout", "product_search", "pay_methods", "order_track", "coupon_apply", "review_add"],
        "soft": ["wishlist_add"],
    },
    "marketplace": {
        "emojis": ["🏪", "🔍", "⭐", "📦"],
        "tone": "commerce",
        "accent": "clean",
        "boost": ["listing_create", "listing_search", "pay_methods", "review_add"],
        "soft": [],
    },
    "restaurant": {
        "emojis": ["🍕", "🍔", "🍽️", "📋"],
        "tone": "warm",
        "accent": "appetizing",
        "boost": ["menu_view", "menu_order", "table_book", "order_status"],
        "soft": ["coupon_apply"],
    },
    "kids": {
        "emojis": ["🧸", "🎈", "🌈", "✨"],
        "tone": "playful",
        "accent": "soft",
        "boost": ["product_search", "wishlist_add", "cart_view", "coupon_apply"],
        "soft": ["review_add"],
        "avoid": ["sec_headers_check", "pipeline_board", "bulk_import", "webhook_set"],
    },
    "electronics": {
        "emojis": ["📱", "💻", "🔌", "⚡"],
        "tone": "technical",
        "accent": "precise",
        "boost": ["product_search", "review_add", "pay_methods", "order_track", "wishlist_add"],
        "soft": [],
    },
    "education": {
        "emojis": ["📚", "🎓", "✅", "📝"],
        "tone": "encouraging",
        "accent": "clear",
        "boost": ["course_list", "quiz_start", "progress_view", "course_enroll"],
        "soft": [],
    },
    "security": {
        "emojis": ["🔒", "🛡️", "🔍", "⚠️"],
        "tone": "professional",
        "accent": "precise",
        "boost": ["sec_dns_check", "sec_tls_check", "sec_headers_check", "sec_tips", "sec_domain_overview"],
        "soft": [],
    },
    "tickets": {
        "emojis": ["🎫", "💬", "📌", "✅"],
        "tone": "supportive",
        "accent": "clear",
        "boost": ["ticket_open", "ticket_status", "ticket_reply", "ticket_list"],
        "soft": [],
    },
    "crm": {
        "emojis": ["📊", "🤝", "📈", "💼"],
        "tone": "professional",
        "accent": "clean",
        "boost": ["lead_capture", "pipeline_board", "deal_create", "followup_set"],
        "soft": [],
    },
    "gaming": {
        "emojis": ["🎮", "🏆", "⚡", "🔥"],
        "tone": "energetic",
        "accent": "fun",
        "boost": ["leaderboard", "contests", "balance"],
        "soft": [],
    },
    "wallet": {
        "emojis": ["💰", "💳", "📱", "✅"],
        "tone": "trust",
        "accent": "clear",
        "boost": ["wallet_balance", "wallet_topup", "pay_methods"],
        "soft": [],
    },
    "booking": {
        "emojis": ["📅", "🗓️", "✅", "⏰"],
        "tone": "calm",
        "accent": "clear",
        "boost": ["table_book"],
        "soft": [],
    },
    "default": {
        "emojis": ["🤖", "✨", "✅", "📌"],
        "tone": "neutral",
        "accent": "clean",
        "boost": [],
        "soft": [],
    },
}

_DOMAIN_ALIAS: dict[str, str] = {
    "اطفال": "kids",
    "أطفال": "kids",
    "kids": "kids",
    "children": "kids",
    "العاب": "kids",
    "العاب اطفال": "kids",
    "لعب": "kids",
    "الكترونيات": "electronics",
    "إلكترونيات": "electronics",
    "electronics": "electronics",
    "موبايل": "electronics",
    "لابتوب": "electronics",
    "tech": "electronics",
    "هاتف": "electronics",
    "جوال": "electronics",
    "مطعم": "restaurant",
    "restaurant": "restaurant",
    "كافيه": "restaurant",
    "cafe": "restaurant",
    "منيو": "restaurant",
    "اكل": "restaurant",
    "أكل": "restaurant",
    "متجر": "shop",
    "shop": "shop",
    "store": "shop",
    "محل": "shop",
    "امن": "security",
    "أمن": "security",
    "security": "security",
    "تعليم": "education",
    "كورس": "education",
    "education": "education",
    "تذكرة": "tickets",
    "تذاكر": "tickets",
    "support": "tickets",
}

# Features treated as advanced (hidden/demoted for beginners)
_ADVANCED_FEATURES = {
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
    "sec_list_reports",
    "deal_create",
}

_HEAVY_FEATURES = {"bulk_import", "role_manage", "webhook_set", "api_endpoint"}


@dataclass
class PersonalizationStyle:
    """Resolved style for one user + one generation request."""

    skill_level: str = "beginner"
    domain: str = "default"
    language_variant: str = "ar"
    complexity: str = "simple"
    tone: str = "neutral"
    accent: str = "clean"
    emojis: list[str] = field(default_factory=lambda: ["🤖", "✨"])
    command_density: str = "few"
    show_advanced: bool = False
    show_admin_panel: bool = False
    prefer_arabic: bool = True
    naming_style: str = "mixed"
    preferred_features: list[str] = field(default_factory=list)
    domain_boost: list[str] = field(default_factory=list)
    domain_soft: list[str] = field(default_factory=list)
    domain_avoid: list[str] = field(default_factory=list)
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
            "preferred_features": list(self.preferred_features),
            "domain_boost": list(self.domain_boost),
            "user_id": self.user_id,
            "reasons": list(self.reasons),
        }


# ── Phrase atoms ────────────────────────────────────────────────────────────
_ATOMS: dict[str, dict[str, dict[str, str]]] = {
    "lets_add": {
        "ar_eg": {"beginner": "يلا نضيف", "intermediate": "يلا نضيف", "expert": "هنضيف"},
        "ar": {"beginner": "لنقم بإضافة", "intermediate": "سنضيف", "expert": "أضف"},
        "en": {"beginner": "Let's add", "intermediate": "We'll add", "expert": "Add"},
    },
    "welcome": {
        "ar_eg": {"beginner": "أهلاً بيك", "intermediate": "مرحباً", "expert": "مرحباً"},
        "ar": {"beginner": "مرحباً بك", "intermediate": "مرحباً", "expert": "أهلاً"},
        "en": {"beginner": "Welcome", "intermediate": "Hi", "expert": "Hello"},
    },
    "help_hint": {
        "ar_eg": {"beginner": "لو محتار اكتب /help", "intermediate": "للتفاصيل: /help", "expert": "/help للأوامر"},
        "ar": {"beginner": "للمساعدة اكتب /help", "intermediate": "التفاصيل عبر /help", "expert": "/help"},
        "en": {"beginner": "Type /help if you need guidance", "intermediate": "See /help for details", "expert": "/help"},
    },
    "success": {
        "ar_eg": {"beginner": "تمام، اتعمل بنجاح", "intermediate": "تم بنجاح", "expert": "تم"},
        "ar": {"beginner": "تم بنجاح", "intermediate": "تم", "expert": "✓"},
        "en": {"beginner": "Done successfully", "intermediate": "Done", "expert": "OK"},
    },
    "failure": {
        "ar_eg": {"beginner": "حصلت مشكلة، جرب تاني", "intermediate": "فشل — راجع المدخلات", "expert": "فشل"},
        "ar": {"beginner": "حدث خطأ، حاول مرة أخرى", "intermediate": "فشل — راجع المدخلات", "expert": "فشل"},
        "en": {"beginner": "Something went wrong, try again", "intermediate": "Failed — check inputs", "expert": "Failed"},
    },
    "suggest_build": {
        "ar_eg": {"beginner": "اقتراحات مناسبة ليك", "intermediate": "اقتراحات أثناء البناء", "expert": "Build gaps"},
        "ar": {"beginner": "اقتراحات مناسبة لك", "intermediate": "اقتراحات أثناء البناء", "expert": "فجوات البناء"},
        "en": {"beginner": "Suggestions for you", "intermediate": "Build suggestions", "expert": "Build gaps"},
    },
    "suggest_improve": {
        "ar_eg": {"beginner": "تحسينات بسيطة بعد التوليد", "intermediate": "تحسينات بعد التوليد", "expert": "Post-build"},
        "ar": {"beginner": "تحسينات بعد التوليد", "intermediate": "تحسينات بعد التوليد", "expert": "تحسينات لاحقة"},
        "en": {"beginner": "Simple improvements", "intermediate": "Post-build improvements", "expert": "Post-build"},
    },
    "suggest_preventive": {
        "ar_eg": {"beginner": "تنبيهات مهمة", "intermediate": "تنبيهات وقائية", "expert": "Risk notes"},
        "ar": {"beginner": "تنبيهات مهمة", "intermediate": "تنبيهات وقائية", "expert": "ملاحظات مخاطر"},
        "en": {"beginner": "Important notes", "intermediate": "Preventive tips", "expert": "Risk notes"},
    },
    "because_you": {
        "ar_eg": {"beginner": "مناسب لمستواك", "intermediate": "مناسب لأسلوبك", "expert": "matches your profile"},
        "ar": {"beginner": "مناسب لمستواك", "intermediate": "مناسب لأسلوبك", "expert": "يتوافق مع ملفك"},
        "en": {"beginner": "fits your level", "intermediate": "fits your style", "expert": "matches your profile"},
    },
    "because_domain": {
        "ar_eg": {"beginner": "شائع في المجال ده", "intermediate": "شائع في هذا المجال", "expert": "domain prior"},
        "ar": {"beginner": "شائع في هذا المجال", "intermediate": "شائع في هذا المجال", "expert": "أولوية المجال"},
        "en": {"beginner": "common in this domain", "intermediate": "common in this domain", "expert": "domain prior"},
    },
    "because_pref": {
        "ar_eg": {"beginner": "من تفضيلاتك السابقة", "intermediate": "من تفضيلاتك", "expert": "your prefs"},
        "ar": {"beginner": "من تفضيلاتك السابقة", "intermediate": "من تفضيلاتك", "expert": "تفضيلاتك"},
        "en": {"beginner": "from your past prefs", "intermediate": "from your prefs", "expert": "your prefs"},
    },
}


def _lang_key(style: PersonalizationStyle) -> str:
    lang = style.language_variant
    if lang in {"ar_eg", "ar", "en"}:
        return lang
    return "ar_eg" if style.prefer_arabic else "en"


def _skill_key(style: PersonalizationStyle) -> str:
    return style.skill_level if style.skill_level in {"beginner", "intermediate", "expert"} else "beginner"


def _atom(key: str, style: PersonalizationStyle) -> str:
    lang = _lang_key(style)
    skill = _skill_key(style)
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


def _text_blob(
    text: str,
    lu: LanguageUnderstandingResult | None,
) -> str:
    parts = [text or ""]
    if lu:
        parts.append(lu.original or "")
        parts.append(lu.normalized or "")
    return " ".join(parts)


def _resolve_domain(
    intent: str | None,
    lu: LanguageUnderstandingResult | None,
    profile: UserProfile | None,
    text: str = "",
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    blob = _text_blob(text, lu)
    blob_l = blob.lower()

    # Longer aliases first for better match
    for alias in sorted(_DOMAIN_ALIAS.keys(), key=len, reverse=True):
        if alias in blob_l or alias in blob:
            key = _DOMAIN_ALIAS[alias]
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
        elif profile.total_builds >= 15 and skill != "expert":
            skill = "expert"
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

    domain, dom_reasons = _resolve_domain(primary, lu, profile, text=text)
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
    prefs = list(profile.preferred_features) if profile else []

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
        preferred_features=prefs,
        domain_boost=list(flavor.get("boost") or []),
        domain_soft=list(flavor.get("soft") or []),
        domain_avoid=list(flavor.get("avoid") or []),
        user_id=user_id,
        reasons=reasons,
    )


def feature_filter_for_skill(
    features: list[str],
    style: PersonalizationStyle,
) -> list[str]:
    """Reduce / keep features according to command density (core stays)."""
    out = list(features)
    if style.domain_avoid:
        out = [f for f in out if f not in set(style.domain_avoid)]
    if style.command_density == "rich" or style.skill_level == "expert":
        return out
    if style.command_density == "few":
        return [f for f in out if f not in _ADVANCED_FEATURES]
    return [f for f in out if f not in _HEAVY_FEATURES]


def adapt_message(
    base: str,
    style: PersonalizationStyle,
    *,
    kind: str = "success",
) -> str:
    """Adapt an existing message string to the user's style."""
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


def score_feature_for_style(feature: str, style: PersonalizationStyle) -> float:
    """0..1 affinity score of a feature under this personalization."""
    score = 0.5
    if feature in style.preferred_features:
        score += 0.35
    if feature in style.domain_boost:
        score += 0.25
    if feature in style.domain_soft:
        score += 0.12
    if feature in style.domain_avoid:
        score -= 0.4
    if feature in _ADVANCED_FEATURES:
        if style.skill_level == "beginner":
            score -= 0.35
        elif style.skill_level == "intermediate":
            score -= 0.1
        else:
            score += 0.08
    if feature in _HEAVY_FEATURES and style.skill_level != "expert":
        score -= 0.25
    return max(0.0, min(1.0, score))


def personalize_suggestions(
    suggestions: list[Any],
    style: PersonalizationStyle,
    *,
    kind: str = "build",
    limit: int | None = None,
) -> list[Any]:
    """Rewrite + reorder L5 suggestions for this user style.

    Expects objects with: feature, label_ar, label_en, confidence, reason, source, kind
    Returns same type instances with personalized fields.
    """
    if not suggestions:
        return []

    emoji = style.primary_emoji()
    out: list[Any] = []

    for s in suggestions:
        feat = getattr(s, "feature", "") or ""
        # Hard filter avoided / too advanced for beginners on build list
        if feat in style.domain_avoid:
            continue
        if kind == "build" and style.skill_level == "beginner" and feat in _ADVANCED_FEATURES:
            continue
        if kind == "preventive" and style.skill_level == "beginner" and feat in _HEAVY_FEATURES:
            continue

        affinity = score_feature_for_style(feat, style)
        conf = float(getattr(s, "confidence", 0.5) or 0.5)
        # Blend original confidence with personalization affinity
        new_conf = min(0.99, conf * 0.65 + affinity * 0.45)

        label_ar = getattr(s, "label_ar", "") or feat
        label_en = getattr(s, "label_en", "") or feat
        # Domain emoji prefix (dynamic, not fixed speech)
        if emoji and emoji not in label_ar:
            label_ar = f"{emoji} {label_ar}"
        if emoji and emoji not in label_en:
            label_en = f"{emoji} {label_en}"

        reason = getattr(s, "reason", "") or ""
        # Append personalization hint (composed, not a fixed final sentence)
        if feat in style.preferred_features:
            hint = _atom("because_pref", style)
            if hint and hint not in reason:
                reason = f"{reason} — {hint}".strip(" —")
        elif feat in style.domain_boost:
            hint = _atom("because_domain", style)
            if hint and hint not in reason:
                reason = f"{reason} — {hint}".strip(" —")
        elif style.skill_level == "beginner":
            hint = _atom("because_you", style)
            if hint and hint not in reason and affinity >= 0.55:
                reason = f"{reason} — {hint}".strip(" —")

        # Rebuild same dataclass-like object
        try:
            new_s = type(s)(
                feature=feat,
                label_ar=label_ar,
                label_en=label_en,
                confidence=new_conf,
                reason=reason,
                source=getattr(s, "source", "prior"),
                kind=getattr(s, "kind", kind),
            )
        except TypeError:
            # Fallback: mutate copy if construction signature differs
            new_s = s
            try:
                new_s.label_ar = label_ar
                new_s.label_en = label_en
                new_s.confidence = new_conf
                new_s.reason = reason
            except Exception:
                pass
        out.append(new_s)

    out.sort(key=lambda x: -float(getattr(x, "confidence", 0) or 0))
    if limit is not None:
        out = out[:limit]
    return out


def suggestion_titles(style: PersonalizationStyle) -> dict[str, tuple[str, str]]:
    """Dynamic section titles for L5 prompts (ar, en)."""
    em = style.primary_emoji()
    return {
        "build": (
            f"{em} {_atom('suggest_build', style)}:",
            f"{em} {_atom('suggest_build', style)}:",
        ),
        "improve": (
            f"💡 {_atom('suggest_improve', style)}:",
            f"💡 {_atom('suggest_improve', style)}:",
        ),
        "preventive": (
            f"⚠️ {_atom('suggest_preventive', style)}:",
            f"⚠️ {_atom('suggest_preventive', style)}:",
        ),
    }


def style_prompt_ar(style: PersonalizationStyle) -> str:
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
        "tickets": "تذاكر دعم",
        "crm": "CRM",
        "gaming": "ألعاب",
        "wallet": "محفظة",
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
    "score_feature_for_style",
    "personalize_suggestions",
    "suggestion_titles",
    "style_prompt_ar",
    "style_prompt_en",
]
