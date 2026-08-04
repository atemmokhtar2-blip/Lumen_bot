"""
Deep Requirement Extractor — knowledge + data models + architecture rules.
Designed for long natural language (3000+ characters).
"""

from __future__ import annotations

import re

from ..ontology.architecture_rules import apply_architecture_rules
from ..ontology.data_models_kb import ENTITY_LIBRARY, resolve_data_models
from ..ontology.knowledge_base import (
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
    FieldSpec,
    FormalBotSpec,
    HandlerSpec,
    LanguageSupport,
    QualityRequirements,
    UIFlow,
)
from .document_structure import analyze_structure


def _clean_name(raw: str | None, full: str) -> str:
    m = re.search(
        r"(?:باسم|named|name[:\s]+)\s*([A-Za-z0-9][A-Za-z0-9 \-_]{1,50})",
        full,
        re.I,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:64]
    if raw:
        name = re.sub(r"\s*[-–—]\s*Telegram.*$", "", raw, flags=re.I)
        name = re.sub(r"\s*V?\d+\.\d+.*$", "", name, flags=re.I)
        name = re.sub(r"Telegram\s*Bot", "", name, flags=re.I).strip()
        m2 = re.search(r"باسم\s+([A-Za-z0-9][A-Za-z0-9 \-_]{1,50})", name)
        if m2:
            return re.sub(r"\s+", " ", m2.group(1)).strip()[:64]
        if 2 <= len(name) <= 64 and not name.startswith("بوت"):
            return name
    for line in full.splitlines()[:15]:
        s = line.strip()
        if 3 < len(s) < 60 and not s.startswith(("#", "-", "•", "بوت")):
            return s[:64]
    return "TelegramBot"


def _section_block(text: str, *titles: str) -> str:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        s = line.strip().lower()
        if any(t.lower() in s for t in titles) and len(line.strip()) < 50:
            start = i + 1
            break
    if start is None:
        return ""
    stop = (
        "الأوامر", "الأزرار", "الميزات", "الفكرة", "الهدف", "طريقة", "الأداء",
        "التصميم", "الكيانات", "نماذج", "commands", "buttons", "features",
    )
    buf = []
    for line in lines[start:]:
        s = line.strip()
        if s and len(s) < 45 and any(s.rstrip(":").startswith(w) or w in s.lower() for w in stop):
            # only break on heading-like lines
            if len(s) < 30 or s.endswith(":"):
                break
        buf.append(line)
    return "\n".join(buf)


def _extract_commands_from_text(text: str) -> list[dict]:
    found = []
    seen = set()
    block = _section_block(text, "الأوامر", "commands", "أوامر")
    search_in = block if block.strip() else text
    for m in re.finditer(
        r"/(?P<cmd>[a-zA-Z][a-zA-Z0-9_]{1,32})\s*[-–—:：]?\s*(?P<desc>[^\n]{0,100})",
        search_in,
    ):
        cmd = m.group("cmd").lower()
        if cmd in seen:
            continue
        seen.add(cmd)
        desc = (m.group("desc") or "").strip() or cmd
        admin = cmd in ("admin", "panel", "stats", "ban", "mute", "broadcast") or "أدمن" in desc
        found.append({"command": cmd, "description": desc[:100], "admin_only": admin})
    return found


def _extract_buttons_from_text(text: str) -> list[dict]:
    buttons = []
    seen = set()
    block = _section_block(text, "الأزرار", "buttons", "أزرار", "القائمة")
    emoji_line = re.compile(
        r"^[\s\-•*]*(?P<label>(?:[🛒🧺📦📞⚙️📋🏠⭐🔥🚀📄💬🛍✅❌🎮🏆📝📊]+)\s*[^\n]{1,40})\s*$"
    )
    for src in (block, text):
        if not (src or "").strip():
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
            buttons.append({"text": label, "callback_data": cb})
        if buttons:
            break
    return buttons


def _map_type(archetype: str) -> BotType:
    return {
        "ecommerce": BotType.ECOMMERCE,
        "ticketing": BotType.TICKETING,
        "admin": BotType.ADMIN,
        "assistant": BotType.ASSISTANT,
        "document": BotType.DOCUMENT,
        "notification": BotType.NOTIFICATION,
        "game": BotType.GAME,
    }.get(archetype, BotType.CUSTOM)


def extract_formal_spec(text: str) -> FormalBotSpec:
    # Long-text safe: normalize once
    full = (text or "").strip()
    if len(full) > 200_000:
        full = full[:200_000]

    structure = analyze_structure(full)
    bot_name = _clean_name(structure.title, full)

    archetype = detect_archetype(full)
    knowledge = enrich_from_archetype(archetype)
    feature_tags_raw = extract_feature_tags(full)
    feature_tag_ids = [f["id"] for f in feature_tags_raw]

    text_cmds = _extract_commands_from_text(full)
    text_btns = _extract_buttons_from_text(full)

    # Seed from knowledge if text incomplete
    if not text_cmds and knowledge.get("default_commands"):
        text_cmds = [
            {"command": n, "description": d, "admin_only": a}
            for n, d, a in knowledge["default_commands"]
        ]
    else:
        # merge knowledge defaults without overriding text
        have = {c["command"] for c in text_cmds}
        for n, d, a in knowledge.get("default_commands") or []:
            if n not in have:
                text_cmds.append({"command": n, "description": d, "admin_only": a})

    if not text_btns and knowledge.get("default_buttons"):
        text_btns = [{"text": t, "callback_data": c} for t, c in knowledge["default_buttons"]]

    # Ensure start/help early
    have = {c["command"] for c in text_cmds}
    if "start" not in have:
        text_cmds.insert(0, {"command": "start", "description": "تشغيل البوت", "admin_only": False})
    if "help" not in have:
        text_cmds.append({"command": "help", "description": "المساعدة", "admin_only": False})

    tlow = full.lower()
    requires_payments = "payments" in feature_tag_ids or any(
        k in tlow for k in ("دفع", "payment", "stripe", "فوري", "checkout")
    )
    requires_admin = "admin_panel" in feature_tag_ids or any(
        k in tlow for k in ("أدمن", "admin", "لوحة الإدارة", "لوحة تحكم")
    )
    requires_queue = (
        "task_queue" in feature_tag_ids
        or "concurrency" in feature_tag_ids
        or any(k in tlow for k in ("عدة مستخدمين", "concurrent", "طابور", "في نفس الوقت"))
    )
    requires_files = "file_handling" in feature_tag_ids or any(
        k in tlow for k in ("ملف", "pdf", "صورة", "رفع", "document")
    )
    mentions_postgres = any(k in tlow for k in ("postgres", "postgresql"))

    services = list(knowledge.get("services") or [])
    integrations = list(knowledge.get("integrations") or ["telegram"])
    handler_names = [h["name"] for h in (knowledge.get("handlers") or [])]

    # Data models from KB
    resolved_models = resolve_data_models(archetype, full)
    model_names = [m["name"] for m in resolved_models]

    ctx = {
        "bot_type": archetype if archetype != "custom" else "custom",
        "buttons": text_btns,
        "commands": text_cmds,
        "services": services,
        "model_names": model_names,
        "integrations": integrations,
        "handler_names": handler_names,
        "feature_tags": feature_tag_ids,
        "requires_payments": requires_payments,
        "requires_admin_panel": requires_admin,
        "requires_async_queue": requires_queue,
        "requires_file_handling": requires_files,
        "mentions_postgres": mentions_postgres,
        "database": "postgres" if mentions_postgres else "sqlite",
        "languages": [],
        "requires_state_management": True,
    }

    ctx, applied = apply_architecture_rules(ctx)

    # Rebuild models after rules may have added model names
    final_model_names = ctx["model_names"]
    data_models: list[DataModelSpec] = []
    for name in final_model_names:
        lib = ENTITY_LIBRARY.get(name)
        if lib:
            data_models.append(
                DataModelSpec(
                    name=name,
                    fields=[n for n, _ in lib],
                    typed_fields=[FieldSpec(name=n, type_hint=ty) for n, ty in lib],
                )
            )
        else:
            # find in resolved
            hit = next((m for m in resolved_models if m["name"] == name), None)
            if hit:
                data_models.append(
                    DataModelSpec(
                        name=name,
                        fields=hit["field_names"],
                        typed_fields=[
                            FieldSpec(name=f["name"], type_hint=f["type"]) for f in hit["fields"]
                        ],
                    )
                )

    handlers = [
        HandlerSpec(
            name=h["name"],
            handler_type=h.get("type", "command"),
            triggers=list(h.get("triggers") or []),
            admin_only=bool(h.get("admin_only", False)),
        )
        for h in (knowledge.get("handlers") or [])
    ]
    # Ensure handlers for all commands from rules
    existing = {h.name for h in handlers}
    for hname in ctx["handler_names"]:
        if hname not in existing and not hname.startswith("cb_"):
            handlers.append(
                HandlerSpec(name=hname, handler_type="command", triggers=[f"/{hname}"])
            )
            existing.add(hname)

    features: list[Feature] = []
    block = _section_block(full, "الميزات", "features", "المميزات")
    for line in (block or full).splitlines():
        cleaned = re.sub(r"^[\s\-•*–—\d\.]+", "", line).strip()
        if 4 < len(cleaned) < 120 and not cleaned.startswith("/") and not cleaned.endswith(":"):
            features.append(Feature(name=cleaned[:80], description=cleaned[:120]))
    for ft in feature_tags_raw:
        features.append(
            Feature(
                name=ft["id"],
                feature_id=ft["id"],
                category=ft["category"],
                description=ft["id"],
            )
        )

    languages: list[LanguageSupport] = []
    for lang in ctx.get("languages") or []:
        if lang == "ar_rtl":
            languages.append(LanguageSupport.ARABIC_RTL)
        elif lang == "en":
            languages.append(LanguageSupport.ENGLISH)
    if any(k in tlow for k in ("العربية", "عربي", "rtl")):
        if LanguageSupport.ARABIC_RTL not in languages:
            languages.append(LanguageSupport.ARABIC_RTL)
    if any(k in tlow for k in ("english", "الإنجليزية")):
        if LanguageSupport.ENGLISH not in languages:
            languages.append(LanguageSupport.ENGLISH)
    if not languages:
        languages = [LanguageSupport.ARABIC]

    idea = structure.section_text("فكرة", "idea", "overview", "وصف")
    description = (idea or full[:1500]).strip()[:3000]
    final_sec = structure.get_section("الهدف النهائي", "final goal", "الهدف")
    final_goal = final_sec.content.strip()[:800] if final_sec else None

    commands = [
        CommandSpec(
            command=c["command"],
            description=c.get("description") or c["command"],
            admin_only=bool(c.get("admin_only")),
        )
        for c in ctx["commands"]
    ]
    buttons = [
        ButtonSpec(text=b["text"], callback_data=b["callback_data"]) for b in (ctx.get("buttons") or text_btns)
    ]

    db = DatabaseChoice.POSTGRES if ctx.get("database") == "postgres" else DatabaseChoice.SQLITE

    return FormalBotSpec(
        bot_name=bot_name,
        bot_type=_map_type(archetype),
        description=description,
        final_goal=final_goal,
        features=features[:80],
        feature_tags=list(ctx["feature_tags"]),
        handlers=handlers,
        data_models=data_models,
        services=list(ctx["services"]),
        integrations=list(ctx["integrations"]),
        ui=UIFlow(
            welcome_message=f"مرحبًا بك في *{bot_name}*\nاختر من القائمة أو استخدم الأوامر.",
            main_buttons=buttons[:12],
            commands=commands[:25],
            show_progress=any(k in full for k in ("حالة", "progress", "جاري")),
        ),
        languages=languages,
        database=db,
        requires_async_queue=requires_queue,
        requires_state_management=bool(ctx.get("requires_state_management", True)),
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
        hard_constraints=[
            *(["requires:payments"] if requires_payments else []),
            *(["requires:admin_panel"] if requires_admin else []),
            *(["requires:async_queue"] if requires_queue else []),
            *(["requires:file_handling"] if requires_files else []),
        ],
        architecture_rules_applied=applied,
        source_sections={s.title: s.content[:500] for s in structure.sections},
    )
