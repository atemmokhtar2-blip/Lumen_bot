"""
Deep Requirement Extractor — knowledge-base driven understanding.
Produces a rich FormalBotSpec that generation assembles from.
"""

from __future__ import annotations

import re

from ..ontology.knowledge_base import (
    ARCHITECTURE_RULES,
    detect_archetype,
    enrich_from_archetype,
    extract_feature_tags,
)
from ..schemas.formal_spec import (
    BotType,
    ButtonSpec,
    CommandSpec,
    DataModelSpec,
    DatabaseChoice,
    Feature,
    FormalBotSpec,
    HandlerSpec,
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


def _section_block(text: str, *titles: str) -> str:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        s = line.strip().lower()
        if any(t.lower() in s for t in titles) and len(line.strip()) < 40:
            start = i + 1
            break
    if start is None:
        return ""
    buf = []
    stop_words = ("الأوامر", "الأزرار", "الميزات", "الفكرة", "الهدف", "طريقة", "الأداء", "التصميم")
    for line in lines[start:]:
        s = line.strip()
        if s and len(s) < 40 and s.rstrip(":").startswith(stop_words):
            break
        if s.endswith(":") and len(s) < 30 and any(w in s for w in stop_words):
            break
        buf.append(line)
    return "\n".join(buf)


def _extract_commands_from_text(text: str) -> list[CommandSpec]:
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
            admin = cmd in ("admin", "panel", "stats", "ban", "mute", "broadcast") or "أدمن" in desc
            commands.append(CommandSpec(command=cmd, description=desc[:80], admin_only=admin))
    return commands


def _extract_buttons_from_text(text: str) -> list[ButtonSpec]:
    buttons: list[ButtonSpec] = []
    seen = set()
    block = _section_block(text, "الأزرار", "buttons", "أزرار", "القائمة")
    emoji_line = re.compile(
        r"^[\s\-•*]*(?P<label>(?:[🛒🧺📦📞⚙️📋🏠⭐🔥🚀📄💬🛍✅❌🎮🏆📝📊]+)\s*[^\n]{1,40})\s*$"
    )
    for src in (block, text):
        if not src.strip():
            continue
        for line in src.splitlines():
            s = line.strip()
            if not s or len(s) > 50:
                continue
            m = emoji_line.match(s)
            if not m:
                continue
            label = m.group("label").strip()
            if label in seen or any(x in label for x in ("المستخدم", "يجب", "أنشئ", "اضغط")):
                continue
            seen.add(label)
            cb = re.sub(r"[^\w]+", "_", label, flags=re.UNICODE).strip("_").lower()[:40] or f"btn_{len(buttons)}"
            buttons.append(ButtonSpec(text=label, callback_data=cb))
        if buttons:
            break
    return buttons


def _map_archetype_to_bot_type(archetype: str) -> BotType:
    mapping = {
        "ecommerce": BotType.ECOMMERCE,
        "ticketing": BotType.TICKETING,
        "admin": BotType.ADMIN,
        "assistant": BotType.ASSISTANT,
        "document": BotType.DOCUMENT,
        "notification": BotType.NOTIFICATION,
        "game": BotType.GAME,
        "custom": BotType.CUSTOM,
    }
    return mapping.get(archetype, BotType.CUSTOM)


def _merge_commands(text_cmds: list[CommandSpec], archetype_cmds: list[tuple]) -> list[CommandSpec]:
    by_name = {c.command: c for c in text_cmds}
    for name, desc, admin in archetype_cmds:
        if name not in by_name:
            by_name[name] = CommandSpec(command=name, description=desc, admin_only=admin)
    # ensure start/help
    if "start" not in by_name:
        by_name["start"] = CommandSpec(command="start", description="تشغيل البوت")
    if "help" not in by_name:
        by_name["help"] = CommandSpec(command="help", description="المساعدة")
    # stable order: start, help, then rest
    ordered = []
    for key in ("start", "help"):
        if key in by_name:
            ordered.append(by_name.pop(key))
    ordered.extend(by_name.values())
    return ordered[:25]


def _merge_buttons(text_btns: list[ButtonSpec], archetype_btns: list[tuple]) -> list[ButtonSpec]:
    if text_btns:
        return text_btns[:12]
    return [ButtonSpec(text=t, callback_data=c) for t, c in archetype_btns][:12]


def extract_formal_spec(text: str) -> FormalBotSpec:
    structure = analyze_structure(text)
    full = structure.raw_text

    bot_name = _clean_name(structure.title, full)
    archetype = detect_archetype(full)
    knowledge = enrich_from_archetype(archetype)
    feature_tags_raw = extract_feature_tags(full)
    feature_tag_ids = [f["id"] for f in feature_tags_raw]

    bot_type = _map_archetype_to_bot_type(archetype)

    # Commands & buttons: text first, enrich from knowledge
    text_cmds = _extract_commands_from_text(full)
    text_btns = _extract_buttons_from_text(full)
    commands = _merge_commands(text_cmds, knowledge.get("default_commands") or [])
    buttons = _merge_buttons(text_btns, knowledge.get("default_buttons") or [])

    # Features from text bullets + lexicon tags
    features: list[Feature] = []
    block = _section_block(full, "الميزات", "features", "المميزات")
    for line in (block or full).splitlines():
        cleaned = re.sub(r"^[\s\-•*–—\d\.]+", "", line).strip()
        if 4 < len(cleaned) < 100 and not cleaned.startswith("/") and not cleaned.endswith(":"):
            features.append(Feature(name=cleaned[:80], description=cleaned[:120]))
    for ft in feature_tags_raw:
        features.append(
            Feature(name=ft["id"], feature_id=ft["id"], category=ft["category"], description=ft["id"])
        )

    # Deep structure from knowledge + flags from text
    handlers = [
        HandlerSpec(
            name=h["name"],
            handler_type=h.get("type", "command"),
            triggers=list(h.get("triggers") or []),
            admin_only=bool(h.get("admin_only", False)),
        )
        for h in (knowledge.get("handlers") or [])
    ]
    data_models = [
        DataModelSpec(name=m["name"], fields=list(m.get("fields") or []))
        for m in (knowledge.get("data_models") or [])
    ]
    services = list(knowledge.get("services") or [])
    integrations = list(knowledge.get("integrations") or ["telegram"])

    t = full.lower()
    requires_payments = "payments" in feature_tag_ids or any(
        k in t for k in ("دفع", "payment", "stripe", "فوري")
    )
    requires_admin = "admin_panel" in feature_tag_ids or any(
        k in t for k in ("أدمن", "admin", "لوحة الإدارة")
    )
    requires_queue = "task_queue" in feature_tag_ids or "concurrency" in feature_tag_ids or any(
        k in t for k in ("عدة مستخدمين", "concurrent", "طابور")
    )
    requires_files = "file_handling" in feature_tag_ids or any(
        k in t for k in ("ملف", "pdf", "صورة", "رفع")
    )
    database = (
        DatabaseChoice.POSTGRES
        if any(k in t for k in ("postgres", "postgresql"))
        else DatabaseChoice.SQLITE
    )

    if requires_payments and "stripe" not in integrations:
        integrations.append("stripe")
    if requires_queue and "redis" not in integrations:
        integrations.append("redis")
    if database == DatabaseChoice.POSTGRES and "postgres" not in integrations:
        integrations.append("postgres")

    # Apply architecture rules (record which fired)
    applied_rules = []
    for rule in ARCHITECTURE_RULES:
        rl = rule.lower()
        if "payment" in rl and requires_payments:
            applied_rules.append(rule)
            if "orders" not in services:
                services.append("orders")
        if "admin" in rl and requires_admin:
            applied_rules.append(rule)
        if "concurrent" in rl and requires_queue:
            applied_rules.append(rule)
        if "every bot must have" in rl:
            applied_rules.append(rule)

    languages: list[LanguageSupport] = []
    if any(k in t for k in ("العربية", "عربي", "rtl")):
        languages.append(LanguageSupport.ARABIC_RTL)
    if any(k in t for k in ("english", "الإنجليزية")):
        languages.append(LanguageSupport.ENGLISH)
    if not languages:
        languages = [LanguageSupport.ARABIC]

    idea = structure.section_text("فكرة", "idea", "overview")
    description = (idea or full[:700]).strip()[:1500]
    final_sec = structure.get_section("الهدف النهائي", "final goal", "الهدف")
    final_goal = final_sec.content.strip()[:500] if final_sec else None

    welcome = f"مرحبًا بك في *{bot_name}*\nاختر من القائمة أو استخدم الأوامر."

    ui = UIFlow(
        welcome_message=welcome,
        main_buttons=buttons,
        commands=commands,
        show_progress=any(k in full for k in ("حالة", "progress", "جاري")),
    )

    hard = []
    if requires_payments:
        hard.append("requires:payments")
    if requires_admin:
        hard.append("requires:admin_panel")
    if requires_queue:
        hard.append("requires:async_queue")
    if requires_files:
        hard.append("requires:file_handling")

    return FormalBotSpec(
        bot_name=bot_name,
        bot_type=bot_type,
        description=description,
        final_goal=final_goal,
        features=features[:60],
        feature_tags=feature_tag_ids,
        handlers=handlers,
        data_models=data_models,
        services=services,
        integrations=integrations,
        ui=ui,
        languages=languages,
        database=database,
        requires_async_queue=requires_queue,
        requires_state_management=True,
        requires_admin_panel=requires_admin,
        requires_payments=requires_payments,
        requires_file_handling=requires_files,
        quality=QualityRequirements(
            high_performance=True,
            full_error_handling=True,
            concurrent_users=requires_queue,
            modular_code=True,
            high_availability=requires_queue,
            clean_extensible=True,
        ),
        hard_constraints=hard,
        architecture_rules_applied=applied_rules,
        source_sections={s.title: s.content[:400] for s in structure.sections},
    )
