"""Stage-1 deep extraction: turn a free-text bot brief into a strict structured spec.

Goal: extract ONLY what the user asked for — name, menu, commands, flows, constraints.
When the user lists explicit menu/commands, generation must not invent extras.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .normalize import normalize_text


@dataclass
class ExplicitCommand:
    """A single user-facing action the bot must implement."""
    id: str
    label_ar: str = ""
    label_en: str = ""
    kind: str = "menu"  # menu | command | flow
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label_ar": self.label_ar,
            "label_en": self.label_en,
            "kind": self.kind,
            "details": self.details,
        }


@dataclass
class BotBrief:
    """Structured understanding of the user's bot request."""
    bot_name: str | None = None
    purpose: str | None = None  # support | shop | booking | ...
    framework: str | None = None  # aiogram | python-telegram-bot
    language: str = "ar"
    menu_items: list[ExplicitCommand] = field(default_factory=list)
    commands: list[ExplicitCommand] = field(default_factory=list)
    flows: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    features_requested: list[str] = field(default_factory=list)
    # When True: generation must stick to extracted menu/commands only
    strict: bool = False
    confidence: float = 0.0
    raw_snippets: dict[str, str] = field(default_factory=dict)

    def all_action_ids(self) -> list[str]:
        seen: list[str] = []
        for c in self.menu_items + self.commands:
            if c.id and c.id not in seen:
                seen.append(c.id)
        return seen

    def to_dict(self) -> dict[str, Any]:
        return {
            "bot_name": self.bot_name,
            "purpose": self.purpose,
            "framework": self.framework,
            "language": self.language,
            "menu_items": [c.to_dict() for c in self.menu_items],
            "commands": [c.to_dict() for c in self.commands],
            "flows": list(self.flows),
            "constraints": list(self.constraints),
            "features_requested": list(self.features_requested),
            "strict": self.strict,
            "confidence": round(self.confidence, 3),
            "action_ids": self.all_action_ids(),
        }


# ── Name extraction ─────────────────────────────────────────────────────────
_NAME_PATTERNS = [
    re.compile(
        r"(?:اسمه|اسمها|يسمى|تسمى|called|named|name\s*[:=])\s*[«\"']?([A-Za-z][\w\-]{1,40}|[\u0600-\u06FF][\w\u0600-\u06FF]{1,40})[»\"']?",
        re.I,
    ),
    re.compile(r"(?:بوت|bot)\s+(?:تيليجرام\s+)?(?:اسمه|اسمها|called)\s+([A-Za-z][\w\-]{1,40})", re.I),
    re.compile(r"\b([A-Z][a-zA-Z]+(?:Help|Bot|Shop|Support|Care|Aid))\b"),
    re.compile(r"(?:بوت|bot)\s+(?:تيليجرام\s+)?(?:ل|لـ|for)?\s*[^\n]{0,40}?(?:اسمه|اسمها)\s+(\S+)", re.I),
]

# ── Slash commands explicit ─────────────────────────────────────────────────
_SLASH_CMD = re.compile(r"/(?:start|help|[a-z][a-z0-9_]{1,32})", re.I)

# ── Menu / list item lines (emoji or bullets) ───────────────────────────────
_MENU_LINE = re.compile(
    r"(?:^|\n)\s*(?:[\U0001F300-\U0001FAFF]|[-•*]|\d+[\).\]])\s*([^\n]{2,80})",
    re.M,
)

# Map Arabic/English labels → stable action ids (capability-ish)
_LABEL_TO_ID: list[tuple[tuple[str, ...], str, str]] = [
    (("المنتجات", "منتجات", "منتج", "products", "catalog", "shop", "كتالوج"), "products", "🛍️ المنتجات"),
    (("متابعة الطلب", "متابعة طلب", "تتبع الطلب", "تتبع طلب", "حالة الطلب", "order track", "track order", "order status", "تتبع"),
     "order_track", "📦 متابعة الطلب"),
    (("طرق الدفع", "الدفع", "دفع", "payment", "pay methods", "مدفوعات"), "payment_methods", "💳 طرق الدفع"),
    (("الشحن", "شحن", "التوصيل", "توصيل", "shipping", "delivery"), "shipping", "🚚 الشحن والتوصيل"),
    (("التواصل مع الدعم", "الدعم", "دعم", "support", "tickets", "ticket", "contact support", "موظف"), "support", "📞 التواصل مع الدعم"),
    (("الأسئلة الشائعة", "faq", "أسئلة شائعة"), "faq", "❓ الأسئلة الشائعة"),
    (("السلة", "cart"), "cart", "🛒 السلة"),
    (("الطلبات", "orders", "طلباتي"), "my_orders", "📋 طلباتي"),
    (("المحفظة", "محفظة", "محفظه", "wallet", "رصيد المحفظة"), "wallet", "💰 المحفظة"),
    (("الكوبونات", "coupon", "كوبون"), "coupons", "🏷️ كوبونات"),
    (("النقاط", "points", "نقاط"), "points", "⭐ النقاط"),
    (("الحجز", "booking", "موعد"), "booking", "📅 الحجز"),
    (("start", "ابدأ", "البداية"), "start", "▶️ ابدأ"),
    (("help", "مساعدة"), "help", "❓ مساعدة"),
]


def _match_label(text: str) -> tuple[str, str] | None:
    low = text.lower().strip()
    norm = normalize_text(text)
    for keys, aid, default_label in _LABEL_TO_ID:
        for k in keys:
            if k.lower() in low or normalize_text(k) in norm or k in text:
                return aid, default_label
    # fallback id from cleaned text
    slug = re.sub(r"[^\w\u0600-\u06FF]+", "_", text.strip())[:32].strip("_").lower()
    if slug:
        return slug or "action", text.strip()[:40]
    return None


def _extract_name(text: str) -> str | None:
    for rx in _NAME_PATTERNS:
        m = rx.search(text)
        if m:
            name = m.group(1).strip().strip("«»\"'")
            if len(name) >= 2:
                return name[:40]
    # "بوت X لـ..." pattern
    m = re.search(r"(?:بوت|bot)\s+([A-Za-z][\w\-]{1,30})", text, re.I)
    if m and m.group(1).lower() not in {"telegram", "aiogram", "python"}:
        return m.group(1)[:40]
    return None


def _extract_framework(text: str) -> str | None:
    low = text.lower()
    if "aiogram" in low:
        return "aiogram"
    if "python-telegram-bot" in low or "ptb" in low or "telegram.ext" in low:
        return "python-telegram-bot"
    return None


def _extract_purpose(text: str) -> str | None:
    low = text.lower()
    norm = normalize_text(text)
    rules = [
        (("خدمة عملاء", "customer service", "customer support", "support bot", "دعم فني", "دعم العملاء", "helpdesk", "help desk"), "support"),
        (("متجر", "ecommerce", "e-commerce", "shop", "store", "بيع", "storefront"), "shop"),
        (("حجز", "booking", "موعد", "عيادة"), "booking"),
        (("تعليمي", "كورس", "education", "course"), "education"),
        (("أمن", "security", "cyber"), "security"),
    ]
    for keys, purpose in rules:
        if any(k in text or k in low or normalize_text(k) in norm for k in keys):
            return purpose
    return None


def _bot_context(text: str) -> bool:
    """True when the utterance is about building/describing a bot."""
    low = (text or "").lower()
    keys = (
        "بوت", "bot", "telegram", "تيليجرام", "اعمل", "سوي", "سوّي", "أبي",
        "عايز", "أريد", "generate", "خدمة عملاء", "متجر", "قائمة", "menu",
        "فيه", "فيها", "يشمل", "with", "commands", "أوامر",
    )
    return any(k in text or k in low for k in keys)


def _extract_menu_and_commands(text: str) -> tuple[list[ExplicitCommand], list[ExplicitCommand]]:
    menu: list[ExplicitCommand] = []
    cmds: list[ExplicitCommand] = []
    seen: set[str] = set()
    raw = text or ""
    low = raw.lower()

    # Explicit slash commands
    for m in _SLASH_CMD.finditer(raw):
        cid = m.group(0).lstrip("/").lower()
        if cid in seen:
            continue
        seen.add(cid)
        cmds.append(ExplicitCommand(id=cid, label_en=cid, kind="command"))

    # Emoji / bullet menu lines
    for m in _MENU_LINE.finditer(raw):
        label = m.group(1).strip()
        if len(label) > 60:
            continue
        matched = _match_label(label)
        if not matched:
            continue
        aid, default_lab = matched
        if aid in seen:
            continue
        seen.add(aid)
        menu.append(
            ExplicitCommand(
                id=aid,
                label_ar=label if any("؀" <= c <= "ۿ" for c in label) else default_lab,
                label_en=aid,
                kind="menu",
                details=label,
            )
        )

    # Inline feature scan — works without "قائمة" if bot-building context
    # e.g. "فيه منتجات ومتابعة طلب ودفع وشحن ودعم"
    inline_gate = _bot_context(raw) or bool(menu) or any(
        w in raw for w in ("قائمة", "menu", "أزرار", "فيها", "فيه", "تشمل", "with", "and")
    )
    if inline_gate:
        for keys, aid, default_lab in _LABEL_TO_ID:
            if aid in seen or aid in {"start", "help"}:
                continue
            hit = False
            norm_raw = normalize_text(raw)
            for k in keys:
                if len(k) <= 1:
                    continue
                if len(k) <= 2 and k not in ("دفع", "شحن", "دعم"):
                    continue
                if k in raw or k.lower() in low or normalize_text(k) in norm_raw:
                    hit = True
                    break
            if hit:
                seen.add(aid)
                menu.append(ExplicitCommand(id=aid, label_ar=default_lab, kind="menu"))

    return menu, cmds


def _extract_flows(text: str) -> list[str]:
    flows: list[str] = []
    low = text.lower()
    pairs = [
        (("رقم الطلب", "order id", "order number", "يتابع الطلب", "متابعة الطلب", "تتبع الطلب", "track order", "order status"), "order_track_by_id"),
        (("أسئلة شائعة", "الأسئلة الشائعة", "faq", "faqs", "يرد تلقائي", "auto reply"), "faq_auto_reply"),
        (("موظف", "support agent", "يحوله", "تحويل للدعم", "قسم الدعم"), "support_handoff"),
        (("حفظ محادثات", "conversation history", "سجل المحادثة"), "save_conversations"),
        (("بياناته هو فقط", "own data only", "خصوصية", "privacy"), "privacy_own_data"),
        (("الموظف", "staff panel", "طلبات الدعم", "لوحة الموظفين"), "staff_support_panel"),
    ]
    for keys, fid in pairs:
        if any(k in text or k in low for k in keys):
            if fid not in flows:
                flows.append(fid)
    return flows


def _extract_constraints(text: str) -> list[str]:
    constraints: list[str] = []
    low = text.lower()
    if any(k in text or k in low for k in ("فقط", "only", "بس", "ما يعملش من دماغه", "لا تضف", "بدون زيادة", "زي ما المستخدم", "من غير زيادة", "exactly")):
        constraints.append("strict_no_extra_commands")
    if any(k in text or k in low for k in ("قابل للتطوير", "scalable", "منظم")):
        constraints.append("modular_structure")
    if any(k in text or k in low for k in ("إعدادات منفصلة", "config", ".env")):
        constraints.append("separate_config")
    if any(k in text or k in low for k in ("قاعدة بيانات", "database", "sqlite", "postgres")):
        constraints.append("database_required")
    if any(k in text or k in low for k in ("نشر", "deploy", "production", "جاهز للتشغيل")):
        constraints.append("production_ready")
    if any(k in text or k in low for k in ("كل عميل يشوف بياناته", "own data", "هو فقط")):
        constraints.append("row_level_privacy")
    return constraints


def _features_from_brief(brief: BotBrief) -> list[str]:
    """Map extracted actions/flows → real registry keys only (no invented extras)."""
    feats: list[str] = ["start", "help", "lang"]
    mapping: dict[str, list[str]] = {
        "products": ["shop_catalog"],  # one menu item = catalog only
        "order_track": ["order_track"],
        "payment_methods": ["pay_methods"],
        "shipping": ["shipping_set"],
        "support": ["ticket_open"],  # support button opens ticket; staff list via flow
        "faq": ["faq_list"],
        "cart": ["cart_view", "cart_add"],
        "my_orders": ["shop_my_orders"],
        "wallet": ["wallet_balance"],
        "coupons": ["coupon_apply"],
        "points": ["points_balance"],
        "booking": ["book_slot"],
        "wallet": ["wallet_balance"],
    }
    for aid in brief.all_action_ids():
        if aid in {"start", "help", "lang"}:
            continue
        for cap in mapping.get(aid, []):
            if cap not in feats:
                feats.append(cap)
    flow_map: dict[str, list[str]] = {
        "order_track_by_id": ["order_track"],
        "faq_auto_reply": ["faq_list"],
        "support_handoff": ["ticket_open"],
        "staff_support_panel": ["ticket_list", "ticket_reply", "ticket_close"],
        "save_conversations": ["note_add", "note_list"],
        "privacy_own_data": [],
    }
    for f in brief.flows:
        for cap in flow_map.get(f, []):
            if cap not in feats:
                feats.append(cap)
    return feats


def extract_bot_brief(text: str) -> BotBrief:
    """Main Stage-1 extractor for bot-building requests."""
    raw = text or ""
    brief = BotBrief()
    brief.bot_name = _extract_name(raw)
    brief.framework = _extract_framework(raw)
    brief.purpose = _extract_purpose(raw)
    if re.search(r"[\u0600-\u06FF]", raw):
        brief.language = "ar"
    elif re.search(r"[A-Za-z]{3,}", raw):
        brief.language = "en"

    menu, cmds = _extract_menu_and_commands(raw)
    brief.menu_items = menu
    brief.commands = cmds
    brief.flows = _extract_flows(raw)
    brief.constraints = _extract_constraints(raw)
    # User-explicit menu/commands captured before soft defaults
    user_menu_n = len(brief.menu_items)
    user_cmd_n = len(brief.commands)
    brief.features_requested = _features_from_brief(brief)

    # Soft domain defaults (NOT strict) when only "بوت متجر" / "بوت حجوزات"
    real = [f for f in brief.features_requested if f not in {"start", "help", "lang"}]
    soft_defaults = False
    if not real and brief.purpose:
        soft_defaults = True
        defaults = {
            "shop": ["shop_catalog", "order_track", "pay_methods"],
            "support": ["ticket_open", "faq_list"],
            "booking": ["book_slot", "ticket_open"],
            "education": ["faq_list"],
        }
        for f in defaults.get(brief.purpose) or []:
            if f not in brief.features_requested:
                brief.features_requested.append(f)
        soft_menu = {
            "shop": ["products", "order_track", "payment_methods"],
            "support": ["support", "faq"],
            "booking": ["booking"],
        }
        if not brief.menu_items:
            for mid in soft_menu.get(brief.purpose) or []:
                brief.menu_items.append(
                    ExplicitCommand(id=mid, label_ar=mid, kind="menu")
                )
        brief.constraints.append("soft_domain_defaults")

    # Strict only from USER-explicit signals — never from soft defaults
    brief.strict = (
        (user_menu_n >= 2 and not soft_defaults)
        or ("strict_no_extra_commands" in brief.constraints)
        or user_cmd_n >= 3
        or (user_menu_n >= 1 and any(k in (raw or "") for k in ("فقط", "بس", "only")))
        or (user_menu_n >= 1 and any(k in (raw or "") for k in ("قائمة", "menu", "/start")))
    )

    score = 0.0
    if brief.bot_name:
        score += 0.2
    if brief.purpose:
        score += 0.15
    if brief.menu_items:
        score += min(0.35, 0.08 * len(brief.menu_items))
    if brief.flows:
        score += min(0.2, 0.05 * len(brief.flows))
    if brief.framework:
        score += 0.05
    if brief.constraints:
        score += 0.05
    brief.confidence = min(0.99, score)

    if brief.bot_name:
        brief.raw_snippets["name"] = brief.bot_name
    if brief.menu_items:
        brief.raw_snippets["menu"] = " | ".join(c.label_ar or c.id for c in brief.menu_items)

    return brief


__all__ = ["BotBrief", "ExplicitCommand", "extract_bot_brief"]
