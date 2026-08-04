"""
Deep Requirement Extractor – high precision for long complex specs.
Extracts name, type, commands, buttons, features, workflow, tech flags.
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
    m = re.search(
        r"(?:باسم|named|name[:\s]+)\s*([A-Za-z0-9][A-Za-z0-9 \-_]{1,40})",
        full,
        re.I,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:64]

    if raw:
        name = re.sub(r"\s*[-–—]\s*Telegram.*$", "", raw, flags=re.I)
        name = re.sub(r"\s*V?\d+\.\d+.*$", "", name, flags=re.I)
        name = re.sub(r"Telegram\s*Bot", "", name, flags=re.I).strip()
        m2 = re.search(r"باسم\s+([A-Za-z0-9][A-Za-z0-9 \-_]{1,40})", name)
        if m2:
            return re.sub(r"\s+", " ", m2.group(1)).strip()[:64]
        if 2 <= len(name) <= 64 and not name.startswith("بوت"):
            return name

    for line in full.splitlines()[:8]:
        s = line.strip()
        if 3 < len(s) < 50 and not s.startswith(("#", "-", "•", "بوت")):
            return s[:64]
    return "TelegramBot"


def _detect_bot_type(text: str, capabilities: list[str]) -> BotType:
    t = text.lower()
    if any(k in t for k in ("متجر", "shop", "store", "منتجات", "شراء", "ecommerce", "سلة", "كتالوج")):
        return BotType.ECOMMERCE
    if any(k in t for k in ("تذاكر", "ticket", "دعم فني", "support ticket", "شكوى")):
        return BotType.TICKETING
    if any(k in t for k in ("لوحة أدمن", "admin panel", "لوحة تحكم")) and not any(
        k in t for k in ("متجر", "منتجات", "سلة")
    ):
        return BotType.ADMIN
    if any(k in t for k in ("لعبة", "game", "نقاط", "تحدي")):
        return BotType.GAME
    if any(k in t for k in ("مساعد", "assistant", "chatgpt", "gpt")):
        return BotType.ASSISTANT
    if any(k in t for k in ("pdf", "مستند", "document designer", "مصمم مستندات")):
        return BotType.DOCUMENT
    if any(k in t for k in ("إشعار جماعي", "broadcast", "notification bot")):
        return BotType.NOTIFICATION
    if any(k in t for k in ("مجتمع", "community", "إدارة جروب")):
        return BotType.COMMUNITY
    return BotType.CUSTOM


def _section_block(text: str, *titles: str) -> str:
    """Extract content under a section heading until next heading."""
    lines = text.splitlines()
    title_re = re.compile(
        r"^(?:#{1,3}\s*)?(" + "|".join(re.escape(t) for t in titles) + r")\s*:?\s*$",
        re.I,
    )
    start = None
    for i, line in enumerate(lines):
        if title_re.match(line.strip()):
            start = i + 1
            break
    if start is None:
        # fuzzy: line contains title word
        for i, line in enumerate(lines):
            low = line.strip().lower()
            if any(t.lower() in low for t in titles) and len(line.strip()) < 40:
                start = i + 1
                break
    if start is None:
        return ""
    buf = []
    for line in lines[start:]:
        s = line.strip()
        if s and len(s) < 40 and not s.startswith(("-", "•", "*", "/", "🛒", "🧺", "📦", "📞", "⚙️")):
            # possible next heading
            if re.match(r"^(الأوامر|الأزرار|الميزات|الفكرة|الهدف|طريقة|الأداء|التصميم)", s):
                break
            if s.endswith(":") and len(s) < 30:
                break
        buf.append(line)
    return "\n".join(buf)


def _extract_commands(text: str) -> list[CommandSpec]:
    commands: list[CommandSpec] = []
    seen = set()
    block = _section_block(text, "الأوامر", "commands", "أوامر")
    search_in = block if block.strip() else text
    for m in re.finditer(
        r"/(?P<cmd>[a-zA-Z][a-zA-Z0-9_]{1,32})\s*[-–—:：]?\s*(?P<desc>[^\n]{0,80})",
        search_in,
    ):
        cmd = m.group("cmd").lower()
        desc = (m.group("desc") or "").strip() or cmd
        if cmd not in seen:
            seen.add(cmd)
            admin = cmd in ("admin", "panel", "stats") or "أدمن" in desc or "admin" in desc.lower()
            commands.append(CommandSpec(command=cmd, description=desc[:80], admin_only=admin))

    # Always ensure start/help
    if "start" not in seen:
        commands.insert(0, CommandSpec(command="start", description="تشغيل البوت"))
    if "help" not in seen:
        commands.append(CommandSpec(command="help", description="المساعدة"))
    return commands[:20]


def _extract_buttons(text: str) -> list[ButtonSpec]:
    buttons: list[ButtonSpec] = []
    seen = set()
    block = _section_block(text, "الأزرار", "buttons", "أزرار", "القائمة")
    search_in = block if block.strip() else ""

    emoji_line = re.compile(
        r"^[\s\-•*]*(?P<label>(?:[🛒🧺📦📞⚙️📋🏠⭐🔥🚀📄💬🛍✅❌]+)\s*[^\n]{1,40})\s*$"
    )
    plain_btn = re.compile(
        r"^[\s\-•*]*(?P<label>(?:المنتجات|السلة|طلباتي|تواصل|لوحة الإدارة|المنتجات|الطلبات|الملف|الإعدادات)[^\n]{0,30})\s*$",
        re.I,
    )

    sources = [search_in] if search_in.strip() else []
    # also scan full text for emoji button lines only
    sources.append(text)

    for src in sources:
        for line in src.splitlines():
            s = line.strip()
            if not s or len(s) > 50:
                continue
            m = emoji_line.match(s) or plain_btn.match(s)
            if not m:
                continue
            label = m.group("label").strip()
            if label in seen or len(label) < 2:
                continue
            # reject narrative sentences
            if any(x in label for x in ("المستخدم", "البوت", "يجب", "عند", "أنشئ", "اضغط")):
                continue
            seen.add(label)
            cb = re.sub(r"[^\w]+", "_", label, flags=re.UNICODE).strip("_").lower()[:40]
            if not cb:
                cb = f"btn_{len(buttons)}"
            buttons.append(ButtonSpec(text=label, callback_data=cb))
        if buttons:
            break

    if not buttons:
        buttons = [ButtonSpec(text="🏠 القائمة الرئيسية", callback_data="main_menu")]
    return buttons[:12]


def _extract_features(text: str) -> list[Feature]:
    features: list[Feature] = []
    block = _section_block(text, "الميزات", "features", "المميزات")
    src = block if block.strip() else text
    for line in src.splitlines():
        cleaned = re.sub(r"^[\s\-•*–—\d\.]+", "", line).strip()
        if 4 < len(cleaned) < 100:
            # skip commands and pure headings
            if cleaned.startswith("/") or cleaned.endswith(":"):
                continue
            features.append(Feature(name=cleaned[:80], description=cleaned[:120]))
    return features[:50]


def _extract_languages(text: str) -> list[LanguageSupport]:
    langs: list[LanguageSupport] = []
    t = text.lower()
    if any(k in t for k in ("العربية", "عربي", "rtl", "العربي")):
        langs.append(LanguageSupport.ARABIC_RTL)
    if any(k in t for k in ("english", "الإنجليزية", "انجليزي")):
        langs.append(LanguageSupport.ENGLISH)
    if any(k in t for k in ("لغتين", "mixed", "معاً", "معًا")):
        if LanguageSupport.MIXED not in langs:
            langs.append(LanguageSupport.MIXED)
    return langs or [LanguageSupport.ARABIC]


def _extract_tech_flags(text: str) -> dict:
    t = text.lower()
    return {
        "requires_async_queue": any(
            k in t for k in ("عدة مستخدمين", "concurrent", "في نفس الوقت", "طابور")
        ),
        "requires_state_management": True,
        "requires_admin_panel": any(
            k in t for k in ("أدمن", "admin", "لوحة الإدارة", "لوحة تحكم")
        ),
        "requires_payments": any(
            k in t for k in ("دفع", "payment", "فوري", "stripe", "تحويل بنكي", "كارت")
        ),
        "requires_file_handling": any(
            k in t for k in ("ملف", "file", "pdf", "صورة", "صور", "رفع")
        ),
        "database": (
            DatabaseChoice.POSTGRES
            if any(k in t for k in ("postgres", "postgresql", "قاعدة بيانات postgres"))
            else DatabaseChoice.SQLITE
        ),
    }


def extract_formal_spec(text: str) -> FormalBotSpec:
    structure = analyze_structure(text)
    full = structure.raw_text

    bot_name = _clean_name(structure.title, full)
    matched = CORE_TAXONOMY.find_matching(full)
    capabilities = sorted(
        {c.canonical_name for c in matched if c.kind.value == "bot_capability"}
    )

    bot_type = _detect_bot_type(full, capabilities)
    features = _extract_features(full)
    commands = _extract_commands(full)
    buttons = _extract_buttons(full)
    languages = _extract_languages(full)
    tech = _extract_tech_flags(full)

    idea = structure.section_text("فكرة", "idea", "overview", "وصف")
    description = (idea or full[:700]).strip()[:1500]

    final_sec = structure.get_section("الهدف النهائي", "final goal", "الهدف")
    final_goal = final_sec.content.strip()[:500] if final_sec else None

    welcome = f"مرحبًا بك في *{bot_name}*"
    if "ترحيب" in full:
        welcome = f"مرحبًا بك في *{bot_name}*\nاختر من القائمة أو استخدم الأوامر."

    ui = UIFlow(
        welcome_message=welcome,
        main_buttons=buttons,
        commands=commands,
        show_progress=any(k in full for k in ("حالة التنفيذ", "progress", "جاري")),
    )

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
        requires_state_management=True,
        requires_admin_panel=tech["requires_admin_panel"],
        requires_payments=tech["requires_payments"],
        requires_file_handling=tech["requires_file_handling"],
        quality=quality,
        hard_constraints=hard,
        source_sections={s.title: s.content[:400] for s in structure.sections},
    )
