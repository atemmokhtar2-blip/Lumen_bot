"""
Deep Requirement Extractor – GENERAL purpose.
Works for any Telegram bot description (shop, admin, tickets, games, PDF, anything).
Extreme precision, zero domain lock-in.
"""

from __future__ import annotations

import re
from typing import List

from ..ontology.telegram_taxonomy import CORE_TAXONOMY
from ..schemas.formal_spec import (
    BotType,
    ButtonSpec,
    CommandSpec,
    DatabaseChoice,
    Feature,
    FormalBotSpec,
    LanguageSupport,
    QualityRequirements,
    UIFlow,
)
from .document_structure import analyze_structure


def _clean_name(raw: str | None, full: str) -> str:
    # Prefer explicit "باسم X" or "named X"
    m = re.search(
        r"(?:باسم|named|name[:\s]+)\s*([A-Za-z0-9][A-Za-z0-9\-_]{1,40})",
        full,
        re.I,
    )
    if m:
        return m.group(1).strip()[:64]

    if raw:
        name = re.sub(r"\s*[-–—]\s*Telegram.*$", "", raw, flags=re.I)
        name = re.sub(r"\s*V?\d+\.\d+.*$", "", name, flags=re.I)
        name = re.sub(r"Telegram\s*Bot", "", name, flags=re.I).strip()
        m2 = re.search(r"باسم\s+([A-Za-z0-9][A-Za-z0-9\-_]{1,40})", name)
        if m2:
            return m2.group(1).strip()[:64]
        if 2 <= len(name) <= 64 and not name.startswith("بوت"):
            return name

    for line in full.splitlines()[:8]:
        s = line.strip()
        if 3 < len(s) < 50 and not s.startswith(("#", "-", "•", "بوت")):
            return s[:64]
    return "TelegramBot"


def _detect_bot_type(text: str, capabilities: list[str]) -> BotType:
    t = text.lower()
    if any(k in t for k in ("متجر", "shop", "store", "منتجات", "شراء", "ecommerce", "سلة")):
        return BotType.ECOMMERCE
    if any(k in t for k in ("تذاكر", "ticket", "دعم", "support", "شكوى")):
        return BotType.TICKETING
    if any(k in t for k in ("أدمن", "admin", "لوحة تحكم", "إدارة")):
        return BotType.ADMIN
    if any(k in t for k in ("لعبة", "game", "نقاط", "تحدي")):
        return BotType.GAME
    if any(k in t for k in ("مساعد", "assistant", "ذكاء", "ai", "gpt")):
        return BotType.ASSISTANT
    if any(k in t for k in ("pdf", "مستند", "document", "تقرير", "فاتورة")):
        return BotType.DOCUMENT
    if any(k in t for k in ("إشعار", "notification", "تنبيه", "broadcast")):
        return BotType.NOTIFICATION
    if any(k in t for k in ("مجتمع", "community", "جروب", "قناة")):
        return BotType.COMMUNITY
    if "document_designer" in capabilities or "text_to_pdf" in capabilities:
        return BotType.DOCUMENT
    return BotType.CUSTOM


def _extract_features(text: str) -> list[Feature]:
    features: list[Feature] = []
    # Simple bullet / numbered extraction
    for line in text.splitlines():
        cleaned = re.sub(r"^[\s\-•*–—\d\.]+", "", line).strip()
        if 5 < len(cleaned) < 120 and not cleaned.endswith(":"):
            # Heuristic: looks like a feature
            if any(k in cleaned for k in ("يجب", "يدعم", "يمكن", "يوجد", "زر", "أمر", "نظام", "ميزة")):
                features.append(Feature(name=cleaned[:80], description=cleaned))
    return features[:40]  # safety cap


def _extract_languages(text: str) -> list[LanguageSupport]:
    langs: list[LanguageSupport] = []
    t = text.lower()
    if any(k in t for k in ("العربية", "عربي", "rtl", "اليمين إلى اليسار", "من اليمين")):
        langs.append(LanguageSupport.ARABIC_RTL)
    if any(k in t for k in ("english", "الإنجليزية", "انجليزي", "en")):
        langs.append(LanguageSupport.ENGLISH)
    if any(k in t for k in ("لغتين", "mixed", "معاً", "معًا", "كلاهما")):
        if LanguageSupport.MIXED not in langs:
            langs.append(LanguageSupport.MIXED)
    return langs or [LanguageSupport.ARABIC]


def _extract_ui(text: str, bot_name: str) -> UIFlow:
    buttons: list[ButtonSpec] = []
    # Look for button-like lines
    for line in text.splitlines():
        m = re.search(r"(📄|🚀|🛒|⚙️|📋|💬|🏠|⭐|🔥)?\s*([^\n]{3,40})", line)
        if m and any(k in line for k in ("زر", "button", "📄", "إنشاء", "ابدأ", "جديد")):
            label = m.group(0).strip()[:40]
            cb = re.sub(r"[^\w]", "_", label)[:30].lower()
            buttons.append(ButtonSpec(text=label, callback_data=cb or "main_action"))

    if not buttons:
        buttons = [ButtonSpec(text="ابدأ", callback_data="start_action")]

    commands = [
        CommandSpec(command="start", description="تشغيل البوت"),
        CommandSpec(command="help", description="المساعدة"),
    ]

    welcome = f"مرحبًا بك في {bot_name}"
    if "ترحيب احترافي" in text or "professional" in text.lower():
        welcome = f"مرحبًا بك في *{bot_name}* – بوت احترافي جاهز لخدمتك."

    return UIFlow(
        welcome_message=welcome,
        main_buttons=buttons[:6],
        commands=commands,
        show_progress=any(k in text for k in ("حالة التنفيذ", "progress", "جاري")),
    )


def _extract_tech_flags(text: str) -> dict:
    t = text.lower()
    return {
        "requires_async_queue": any(k in t for k in ("عدة مستخدمين", "concurrent", "في نفس الوقت", "طابور")),
        "requires_state_management": True,  # almost always needed
        "requires_admin_panel": any(k in t for k in ("أدمن", "admin", "لوحة", "إدارة")),
        "requires_payments": any(k in t for k in ("دفع", "payment", "بطاقة", "stripe", "paypal", "فوري")),
        "requires_file_handling": any(k in t for k in ("ملف", "file", "pdf", "صورة", "مستند", "رفع")),
        "database": (
            DatabaseChoice.POSTGRES
            if any(k in t for k in ("postgres", "postgresql", "قاعدة بيانات قوية", "إنتاج"))
            else DatabaseChoice.SQLITE
        ),
    }


def extract_formal_spec(text: str) -> FormalBotSpec:
    """
    General-purpose extreme-precision extractor.
    Works for any bot description.
    """
    structure = analyze_structure(text)
    full = structure.raw_text

    bot_name = _clean_name(structure.title, full)

    # Capabilities from ontology (still useful as signals)
    matched = CORE_TAXONOMY.find_matching(full)
    capabilities = sorted({c.canonical_name for c in matched if c.kind.value == "bot_capability"})

    bot_type = _detect_bot_type(full, capabilities)
    features = _extract_features(full)
    languages = _extract_languages(full)
    ui = _extract_ui(full, bot_name)
    tech = _extract_tech_flags(full)

    idea = structure.section_text("فكرة", "idea", "overview", "وصف")
    description = (idea or full[:700]).strip()[:1500]

    final_sec = structure.get_section("الهدف النهائي", "final goal", "الهدف")
    final_goal = final_sec.content.strip()[:500] if final_sec else None

    quality = QualityRequirements(
        high_performance=True,
        full_error_handling=any(k in full for k in ("معالجة الأخطاء", "error", "استقرار")),
        concurrent_users=tech["requires_async_queue"],
        modular_code=True,
        high_availability=any(k in full for k in ("استقرار", "availability")),
        clean_extensible=True,
    )

    hard = []
    if tech["requires_payments"]:
        hard.append("requires:payments")
    if tech["requires_admin_panel"]:
        hard.append("requires:admin_panel")
    if tech["requires_file_handling"]:
        hard.append("requires:file_handling")
    if tech["requires_async_queue"]:
        hard.append("requires:async_queue")

    return FormalBotSpec(
        bot_name=bot_name,
        bot_type=bot_type,
        description=description,
        final_goal=final_goal,
        capabilities=capabilities,
        features=features,
        ui=ui,
        languages=languages,
        database=tech["database"],
        requires_async_queue=tech["requires_async_queue"],
        requires_state_management=tech["requires_state_management"],
        requires_admin_panel=tech["requires_admin_panel"],
        requires_payments=tech["requires_payments"],
        requires_file_handling=tech["requires_file_handling"],
        quality=quality,
        hard_constraints=hard,
        source_sections={s.title: s.content[:400] for s in structure.sections},
    )
