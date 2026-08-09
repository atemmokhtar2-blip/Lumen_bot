"""
Deep Requirement Extractor — text-grounded only (no KB command/model packs).
Designed for long natural language (3000+ characters).
"""

from __future__ import annotations

import re

from ..ontology.architecture_rules import apply_architecture_rules
from ..ontology.data_models_kb import resolve_data_models
from ..ontology.knowledge_base import (
    extract_feature_tags,
)
from ..schemas.formal_spec import (
    RoleSpec,
    ArchitectureSpec,
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
    # Prefer short explicit names: باسم X / اسمه X / named X
    m = re.search(
        r"(?:باسم|اسمه|اسمها|named|name[:\s]+)\s*([A-Za-z][A-Za-z0-9 \-_]{0,40})",
        full,
        re.I,
    )
    if m:
        cand = re.sub(r"\s+", " ", m.group(1)).strip()[:64]
        if 2 <= len(cand) <= 40:
            return cand
    # Latin brand-like tokens (ShopX, ShopX Pro) — case sensitive capital start
    m = re.search(r"\b([A-Z][A-Za-z0-9]{1,30}(?:\s+[A-Z][A-Za-z0-9]{1,20})?)\b", full)
    if m:
        return m.group(1).strip()[:64]
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
        if 3 < len(s) < 40 and not s.startswith(("#", "-", "•", "بوت", "عايز", "اعمل")):
            if re.match(r"^[A-Za-z0-9][A-Za-z0-9 \-_]{1,38}$", s):
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
    """
    Extract commands grounded in the user text only.
    Patterns (no domain packs):
      - /cmd tokens
      - lines under أوامر/commands sections
      - "الأمر X" / "command X" / "أمر: name"
      - quoted command names in Arabic lists
    """
    found: list[dict] = []
    seen: set[str] = set()

    def _add(cmd: str, desc: str = "", admin: bool | None = None, roles: list[str] | None = None) -> None:
        cmd = (cmd or "").strip().lower().lstrip("/")
        cmd = re.sub(r"[^a-z0-9_]", "", cmd)
        if not cmd or len(cmd) < 2 or cmd in seen:
            return
        if cmd in (
            "http", "https", "www", "command", "commands", "cmd",
            "bot", "telegram", "python", "true", "false", "none",
            "postgresql", "postgres", "sqlite", "mysql", "redis",
            "docker", "aiogram", "pyrogram",
        ):
            return
        seen.add(cmd)
        d = (desc or cmd).strip()[:100]
        # Extract roles from desc if present [roles: user, admin]
        extracted_roles = list(roles or [])
        rm = re.search(r"\[roles:\s*([^\]]+)\]", d)
        if rm:
            extracted_roles.extend([r.strip() for r in rm.group(1).split(",")])
            d = re.sub(r"\[roles:\s*[^\]]+\]", "", d).strip()
        
        is_admin = admin if admin is not None else (
            cmd in ("admin", "panel", "stats", "ban", "mute", "broadcast")
            or any(k in d for k in ("أدمن", "admin", "إدارة", "مشرف"))
            or "admin" in extracted_roles
        )
        found.append({
            "command": cmd, 
            "description": d or cmd, 
            "admin_only": bool(is_admin),
            "roles": list(set(extracted_roles))
        })

    # 1) slash tokens anywhere
    for m in re.finditer(r"/(?P<cmd>[a-zA-Z][a-zA-Z0-9_]{1,32})\b", text):
        rest = text[m.end(): m.end() + 100]
        dm = re.match(r"\s*[-–—:：]\s*([^/\n]{1,80})", rest)
        desc = dm.group(1).strip() if dm else m.group("cmd")
        _add(m.group("cmd"), desc)

    # 2) section: الأوامر / commands
    block = _section_block(text, "الأوامر", "commands", "أوامر البوت", "bot commands")
    for src in (block,):
        if not (src or "").strip():
            continue
        for line in src.splitlines():
            s = line.strip()
            if not s:
                continue
            # /cmd — desc
            m = re.match(r"^[\s\-•*\d\.]*/*([a-zA-Z][a-zA-Z0-9_]{1,32})\s*[-–—:：]?\s*(.*)$", s)
            if m and not s.lower().startswith("http"):
                _add(m.group(1), m.group(2) or m.group(1))
                continue
            # أمر name أو الأمر name
            m2 = re.search(
                r"(?:الأمر|امر|command)\s*[:=]?\s*/*([a-zA-Z][a-zA-Z0-9_]{1,32})",
                s,
                re.I,
            )
            if m2:
                _add(m2.group(1), s)

    # 3) prose: "أمر /foo" or "command foo"
    for m in re.finditer(
        r"(?:الأمر|امر|أمر|command)\s+/*([a-zA-Z][a-zA-Z0-9_]{1,32})",
        text,
        re.I,
    ):
        _add(m.group(1))

    # 4) numbered list items that are clearly command names (ascii token)
    for m in re.finditer(
        r"(?:^|\n)\s*(?:\d+|[\u0660-\u0669]+)[\.\)]\s*/*([a-zA-Z][a-zA-Z0-9_]{1,32})\b\s*[-–—:]?\s*([^\n]{0,80})",
        text,
    ):
        _add(m.group(1), m.group(2))

    return found


def _extract_buttons_from_text(text: str) -> list[dict]:
    """
    Buttons from dedicated sections, inline mentions, and menu labels — text only.
    Stronger extraction for long complex specs (no domain packs).
    """
    buttons: list[dict] = []
    seen: set[str] = set()

    def _add(label: str) -> None:
        label = re.sub(r"\s+", " ", (label or "").strip())
        # strip trailing punctuation
        label = re.sub(r"[.،,;:]+$", "", label).strip()
        if not label or label in seen or len(label) > 48 or len(label) < 2:
            return
        # reject instructional / narrative phrases
        bad = (
            "المستخدم", "يجب", "أنشئ", "اضغط على", "http", "يقوم", "يعرض",
            "يطلب", "ثم ", "إذا ", "لو ", "when ", "then ", "user ",
        )
        if any(x in label for x in bad):
            return
        if label.startswith(("/", "#", "http")):
            return
        seen.add(label)
        cb = re.sub(r"[^\w]+", "_", label, flags=re.UNICODE).strip("_").lower()[:40]
        if not cb:
            cb = f"btn_{len(buttons)}"
        buttons.append({"text": label, "callback_data": cb})

    block = _section_block(
        text, "الأزرار", "buttons", "أزرار", "القائمة", "القائمه", "menu",
        "أزرار تفاعلية", "inline buttons", "keyboard",
        "القائمة الرئيسية", "main menu", "menu buttons",
    )
    emoji_line = re.compile(
        r"^[\s\-•*]*(?P<label>(?:[\U0001F300-\U0001FAFF\u2600-\u27BF]+)\s*[^\n]{1,40})\s*$"
    )

    # 1) Dedicated buttons section first
    if block.strip():
        for line in block.splitlines():
            s = line.strip()
            if not s or len(s) > 50:
                continue
            m = emoji_line.match(s)
            if m:
                _add(m.group("label").strip())
                continue
            m2 = re.match(r"^[\s\-•*\d\.]+(.+)$", s)
            if m2:
                _add(m2.group(1).strip())
                continue
            if 2 <= len(s) <= 40 and not s.endswith(":") and "/" not in s:
                _add(s)

    # 2) Inline patterns anywhere: زر "X" / button "X" / [X] / «X»
    for m in re.finditer(
        r"(?:زر|button|btn)\s*[:=]?\s*[«\"'\[]([^»\"'\]]{2,40})[»\"'\]]",
        text,
        re.I,
    ):
        _add(m.group(1).strip())
    for m in re.finditer(
        r"[«\"\[]([^\n»\"\]]{2,30})[»\"\]]\s*(?:\(زر\)|زر|button)",
        text,
        re.I,
    ):
        _add(m.group(1).strip())

    # 3) "أزرار: A, B, C" or "buttons: A / B / C"
    for m in re.finditer(
        r"(?:الأزرار|أزرار|buttons|menu)\s*[:=]\s*([^\n]{5,120})",
        text,
        re.I,
    ):
        chunk = m.group(1)
        for part in re.split(r"[,،/|•\-]+", chunk):
            part = part.strip()
            if 2 <= len(part) <= 40:
                _add(part)

    # 4) Fallback: short emoji+label lines in full text (if still empty)
    if not buttons:
        for line in text.splitlines():
            s = line.strip()
            if not s or len(s) > 45:
                continue
            m = emoji_line.match(s)
            if m:
                _add(m.group("label").strip())

    return buttons[:30]


def _map_type(archetype: str) -> BotType:
    """Always CUSTOM — domain archetypes removed."""
    _ = archetype
    return BotType.CUSTOM




# ---------------------------------------------------------------------------
# Long-spec deep extraction (generic — any domain, no canned bot templates)
# ---------------------------------------------------------------------------

_ROLE_HEADERS = re.compile(
    r"^(?:#{1,3}\s*)?(Admin|Manager|Driver|Customer|الأدمن|المدير|السائق|العميل|"
    r"مشرف|مدير|مستخدم)\s*:?\s*$",
    re.I | re.M,
)

_PERM_LINE = re.compile(
    r"^[\s\-•*]+(.{2,80})$",
)

_LAYER_WORDS = [
    "handlers", "services", "repositories", "middlewares", "filters",
    "models", "configurations", "utilities", "domain", "usecases",
    "handlers", "services", "repositories",
]


def _extract_bot_name_explicit(text: str, fallback: str) -> str:
    m = re.search(
        r"(?:اسم\s*البوت|bot\s*name)\s*:?\s*\n?\s*([A-Za-z][A-Za-z0-9_\-]{1,40})",
        text,
        re.I,
    )
    if m:
        return m.group(1).strip()[:64]
    m2 = re.search(r"\b([A-Z][A-Za-z0-9]{2,30})\b", text)
    # only if near "اسم" or "bot"
    if m2 and re.search(r"(اسم\s*البوت|bot\s*name|Delivery)", text, re.I):
        # prefer explicit line after اسم البوت
        pass
    m3 = re.search(r"اسم\s*البوت\s*:?\s*([^\n]{2,40})", text, re.I)
    if m3:
        name = re.sub(r"[^\w\-]", "", m3.group(1).strip())
        if len(name) >= 2:
            return name[:64]
    return fallback


def _extract_framework(text: str) -> str:
    t = text.lower()
    if "aiogram" in t:
        return "aiogram"
    if "pyrogram" in t:
        return "pyrogram"
    if "telebot" in t or "pytelegram" in t:
        return "pytelegrambotapi"
    if "python-telegram-bot" in t or "ptb" in t:
        return "python-telegram-bot"
    return "python-telegram-bot"


def _extract_architecture(text: str) -> "ArchitectureSpec":
    t = text.lower()
    style = ""
    if "clean architecture" in t or "cleanarchitecture" in t or "معمارية نظيفة" in t:
        style = "clean_architecture"
    elif "layered" in t or "طبقات" in t:
        style = "layered"
    elif "modular" in t or "modular" in t or "قابلًا للتوسع" in t or "قابل للتوسع" in t:
        style = "modular"
    layers = []
    for w in _LAYER_WORDS:
        if re.search(rf"\b{w}\b", text, re.I):
            if w not in layers:
                layers.append(w)
    di = bool(re.search(r"dependency\s*injection|حقن\s*الاعتماد", text, re.I))
    deploy = []
    for d in ("railway", "docker", "docker-compose", "kubernetes", "heroku"):
        if d in t:
            deploy.append(d)
    return ArchitectureSpec(
        style=style or ("clean_architecture" if layers else ""),
        layers=layers,
        dependency_injection=di,
        framework=_extract_framework(text),
        deploy_targets=deploy,
    )



def _extract_roles(text: str) -> list:
    """
    Extract roles + permissions from text structure — no fixed domain packs.
    Supports: standalone role headers, "الأدوار" section, Role: lines.
    """
    roles: list[RoleSpec] = []
    lines = text.splitlines()

    role_header = re.compile(
        r"^(?:#{1,3}\s*)?(?P<name>Admin|Manager|Driver|Customer|Owner|User|"
        r"الأدمن|الادمن|المدير|السائق|العميل|المشرف|مشرف|مدير|سائق|عميل|مستخدم|مالك)\s*:?\s*$",
        re.I,
    )
    # inline: الدور: السائق
    inline_role = re.compile(
        r"(?:الدور|role)\s*[:=]\s*(?P<name>[\w\u0600-\u06FF]{2,30})",
        re.I,
    )

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = role_header.match(line)
        if not m:
            im = inline_role.search(line)
            if im:
                roles.append(RoleSpec(name=im.group("name").strip(), permissions=[]))
            i += 1
            continue
        rname = m.group("name").strip()
        perms: list[str] = []
        j = i + 1
        while j < len(lines):
            ln = lines[j].strip()
            if role_header.match(ln) or inline_role.search(ln):
                break
            if ln.startswith("=") and len(ln) >= 5:
                break
            if re.search(
                r"^(?:إشعارات|صلاحيات النظام|Logging|Error Handling|Dockerfile|"
                r"Environment|Production|الأوامر|الأزرار)\b",
                ln,
                re.I,
            ):
                break
            if ln in ("يمكنه:", "يمكنه", "permissions:", "can:", "صلاحياته:", "صلاحيات:"):
                j += 1
                continue
            if ln.startswith(("-", "•", "*", "–")) or (
                2 < len(ln) < 100
                and not ln.endswith(":")
                and not ln.lower().startswith("http")
            ):
                perm = ln.lstrip("-•*– \t").strip()
                if perm and perm not in perms and not role_header.match(perm):
                    perms.append(perm[:100])
            j += 1
            if j - i > 60:
                break
        roles.append(RoleSpec(name=rname, permissions=perms[:30]))
        i = j

    # section titled الأدوار: collect headers inside
    sec = _section_block(text, "الأدوار", "roles", "Roles", "الصلاحيات")
    if sec:
        for m in role_header.finditer(sec):
            name = m.group("name").strip()
            if not any(r.name.lower() == name.lower() for r in roles):
                roles.append(RoleSpec(name=name, permissions=[]))

    best: dict[str, RoleSpec] = {}
    for r in roles:
        key = r.name.lower()
        if key not in best or len(r.permissions) > len(best[key].permissions):
            best[key] = r
    return list(best.values())


def _extract_flow_steps(text: str) -> list[str]:
    """
    Ordered behavioral steps from text:
      - /start narrative blocks
      - numbered / Arabic numbered lists
      - إذا / ثم / يقوم chains
      - طريقة العمل / workflow sections
    """
    steps: list[str] = []
    seen: set[str] = set()

    def _push(s: str) -> None:
        s = re.sub(r"^[\-•*\d\.\)\s\u0660-\u0669]+", "", (s or "").strip())
        s = re.sub(r"\s+", " ", s).strip()
        if 3 < len(s) < 160 and s not in seen:
            seen.add(s)
            steps.append(s)

    # A) /start narrative window
    m = re.search(
        r"(?:عند\s*الضغط\s*على\s*/start|/start\s*:?)(.{0,1200})",
        text,
        re.I | re.S,
    )
    if m:
        for ln in m.group(1).splitlines():
            s = ln.strip()
            if re.match(r"^[\-•*\d]", s) or s.startswith(("إذا", "لو", "يقوم", "ثم", "بعدها", "ويرسل", "يعرض")):
                _push(s)
            if len(steps) >= 15:
                break

    # B) workflow section via flow_extractor helpers (inline to avoid cycles)
    section = ""
    lines = text.splitlines()
    start_i = None
    for i, line in enumerate(lines):
        s = line.strip().lower()
        if any(k in s for k in ("طريقة العمل", "workflow", "how it works", "خطوات", "السيناريو")) and len(s) < 48:
            start_i = i + 1
            break
    if start_i is not None:
        buf = []
        for line in lines[start_i:]:
            s = line.strip()
            if s and len(s) < 28 and any(
                k in s for k in ("الأوامر", "الأزرار", "الميزات", "commands", "buttons", "الأدوار")
            ):
                break
            buf.append(line)
        section = "\n".join(buf)

    body = section if section.strip() else text
    for m in re.finditer(
        r"(?:^|\n)\s*(?:\d+|[\u0660-\u0669]+)[\.\)\-\:]\s*([^\n]{5,160})",
        body,
    ):
        _push(m.group(1))

    # C) conditional chains in prose
    for m in re.finditer(
        r"((?:إذا|لو)\s+[^\n.]{5,100}(?:\.|$))",
        text,
    ):
        _push(m.group(1))
    for m in re.finditer(
        r"((?:ثم|بعدها|بعد ذلك)\s+[^\n.]{5,100})",
        text,
    ):
        _push(m.group(1))

    return steps[:25]


def _extract_quality_flags(text: str) -> dict:
    t = text.lower()
    return {
        "requires_notifications": bool(re.search(r"إشعار|notification", text, re.I)),
        "requires_logging": bool(re.search(r"logging|سجل|لوج", text, re.I)),
        "requires_rbac": bool(
            re.search(r"صلاحيات|rbac|permissions|لا يسمح لأي مستخدم", text, re.I)
        ),
        "requires_docker": bool(re.search(r"dockerfile|docker-compose|\bdocker\b", text, re.I)),
        "error_handling": bool(re.search(r"error\s*handling|معالجة\s*أخطاء|بدون توقف", text, re.I)),
        "env_only": bool(re.search(r"environment\s*variables|\.env|لا يتم وضع أي مفاتيح", text, re.I)),
    }


def extract_formal_spec(text: str) -> FormalBotSpec:
    # Long-text safe: normalize once
    full = (text or "").strip()
    if len(full) > 200_000:
        full = full[:200_000]

    structure = analyze_structure(full)
    bot_name = _clean_name(structure.title, full)
    bot_name = _extract_bot_name_explicit(full, bot_name)

    arch = _extract_architecture(full)
    roles = _extract_roles(full)
    flow_steps = _extract_flow_steps(full)
    qflags = _extract_quality_flags(full)

    archetype = "CUSTOM"  # packs removed; formal path uses DSL
    # Long-spec: multi-role ops platforms / meta bot-builders must stay custom
    _low = full.lower()
    if any(k in full for k in ("توصيل", "سائق", "Delivery")) or (
        "driver" in _low and "customer" in _low
    ):
        if archetype in ("game", "utility", "ecommerce"):
            archetype = "custom"
    # Meta / bot-builder hard override (belt-and-suspenders with detect_archetype)
    if any(
        s in full or s in _low
        for s in (
            "بناء بوت", "بناء بوتات", "بوت بناء", "صانع بوتات", "مولد بوتات",
            "bot builder", "bot generator", "create bots", "build bots",
            "meta bot", "meta-bot", "بوت يبني", "يبني بوتات", "انشاء بوتات",
            "إنشاء بوتات", "generate bot", "bot factory", "ai agent", "محرك بوتات",
        )
    ):
        archetype = "custom"
    # Archetype is soft labeling only — NEVER injects commands/buttons/handlers.
    feature_tags_raw = extract_feature_tags(full)
    feature_tag_ids = [f["id"] for f in feature_tags_raw]

    text_cmds = _extract_commands_from_text(full)
    text_btns = _extract_buttons_from_text(full)

    # Structural minimum only — never KB default_commands / default_buttons
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

    # Services / handlers / integrations — grounded, not from archetype packs
    services: list[str] = []
    if requires_files:
        services.append("storage")
    if requires_queue:
        services.append("task_queue")
    if requires_payments:
        services.append("payments")
    # Derive dedicated services from command stems so /new_bot ≠ cart
    _svc_skip = {"start", "help", "menu", "cancel"}
    for c in text_cmds:
        cmd = (c.get("command") or "").lower()
        if not cmd or cmd in _svc_skip:
            continue
        # group bot-related commands under a bots service
        if any(k in cmd for k in ("bot", "bots", "template", "wizard")):
            if "bots" not in services:
                services.append("bots")
            continue
        if cmd not in services and len(cmd) > 2:
            services.append(cmd)
    integrations = ["telegram"]
    if mentions_postgres:
        integrations.append("postgres")
    if requires_queue:
        integrations.append("redis")
    handler_names = [c["command"] for c in text_cmds]

    # Data models from TEXT signals only (see resolve_data_models)
    resolved_models = resolve_data_models(archetype, full)

    # Explicit section: الكيانات / entities — Student (id, name, email)
    _ent_block = _section_block(
        full,
        "الكيانات", "كيانات", "entities", "النماذج", "نماذج البيانات",
        "data models", "models",
    )
    _explicit_models: list[dict] = []
    _seen_ent: set[str] = set()
    for _line in (_ent_block or "").splitlines():
        _s = re.sub(r"^[\s\-•*\d\.]+", "", _line.strip()).strip()
        if not _s:
            continue
        _m = re.match(
            r"^[«\"']?([A-Za-z][A-Za-z0-9_]{1,40})[»\"']?\s*"
            r"(?:[\(:：]\s*([^\)\n]{1,120})[\)]?)?",
            _s,
        )
        if not _m:
            continue
        _ename = _m.group(1)
        if _ename.lower() in _seen_ent:
            continue
        _seen_ent.add(_ename.lower())
        _line_rest = _line[_m.end():].strip()
        _fields_raw = _m.group(2) or "id"
        _relations = []
        if "العلاقات:" in _line_rest:
            _rel_part = _line_rest.split("العلاقات:")[1].strip()
            for _r in re.split(r"[,،;]+", _rel_part):
                _rm = re.search(r"(\w+)\s+with\s+(\w+)", _r)
                if _rm:
                    _relations.append({"type": _rm.group(1), "target": _rm.group(2)})
        
        _fnames = []
        _typed = []
        for p in re.split(r"[,،/;|]+", _fields_raw):
            p = p.strip()
            if not p: continue
            if ":" in p:
                fn, ft = p.split(":", 1)
                fn = re.sub(r"[^a-zA-Z0-9_]", "", fn).lower()
                _fnames.append(fn)
                _typed.append({"name": fn, "type": ft.strip()})
            else:
                fn = re.sub(r"[^a-zA-Z0-9_]", "", p).lower()
                _fnames.append(fn)
                _typed.append({"name": fn, "type": "str"})

        if not _fnames:
            _fnames = ["id"]
            _typed = [{"name": "id", "type": "str"}]
        _explicit_models.append({
            "name": _ename[:1].upper() + _ename[1:],
            "field_names": _fnames,
            "fields": _typed,
            "relations": _relations,
        })
    for _m in re.finditer(
        r"\b([A-Z][A-Za-z0-9_]{1,40})\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\s*,\s*[a-zA-Z_][a-zA-Z0-9_]*){0,12})\s*\)",
        full,
    ):
        _ename = _m.group(1)
        if _ename.lower() in _seen_ent:
            continue
        _seen_ent.add(_ename.lower())
        _fnames = [p.strip().lower() for p in _m.group(2).split(",")]
        _explicit_models.append({
            "name": _ename,
            "field_names": _fnames,
            "fields": [{"name": f, "type": "str"} for f in _fnames],
        })
    if _explicit_models:
        resolved_models = _explicit_models + [
            m for m in resolved_models
            if str(m.get("name", "")).lower() not in _seen_ent
        ]
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
    from ..schemas.formal_spec import DataModelRelation
    for name in final_model_names:
        # Prefer text-grounded resolve_data_models — never dump full ENTITY_LIBRARY packs
        hit = next((m for m in resolved_models if m["name"] == name), None)
        if hit:
            data_models.append(
                DataModelSpec(
                    name=name,
                    fields=hit["field_names"],
                    typed_fields=[
                        FieldSpec(name=f["name"], type_hint=f["type"]) for f in hit["fields"]
                    ],
                    relations=[DataModelRelation(target=r["target"], type=r["type"]) for r in hit.get("relations", [])],
                )
            )
            continue
        # unknown name: minimal structural fields only
        data_models.append(
            DataModelSpec(
                name=name,
                fields=["id"],
                typed_fields=[FieldSpec(name="id", type_hint="str")],
            )
        )

    # Handlers only from text/rule command names — never archetype handler packs
    handlers = []
    existing: set[str] = set()
    for hname in ctx["handler_names"]:
        if hname not in existing and not hname.startswith("cb_"):
            admin = any(
                c.get("command") == hname and c.get("admin_only") for c in ctx.get("commands") or []
            )
            handlers.append(
                HandlerSpec(
                    name=hname,
                    handler_type="command",
                    triggers=[f"/{hname}"],
                    admin_only=bool(admin),
                )
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
            roles=list(c.get("roles") or []),
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
        roles=roles,
        architecture=arch,
        requires_notifications=qflags["requires_notifications"],
        requires_logging=qflags["requires_logging"],
        requires_rbac=qflags["requires_rbac"] or bool(roles),
        requires_docker=qflags["requires_docker"],
        flow_steps=flow_steps,
        source_sections={s.title: s.content[:500] for s in structure.sections},
    )
