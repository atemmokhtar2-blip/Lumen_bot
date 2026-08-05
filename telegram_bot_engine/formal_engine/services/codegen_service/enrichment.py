"""
Deterministic contract enrichment for codegen.

Uses ONLY ProgramContract fields (feature_tags, entities, services, tech).
Never reads raw user natural language.
"""

from __future__ import annotations

from ...schemas.program_contract import (
    ButtonUnit,
    CommandUnit,
    ProgramContract,
    ServiceUnit,
)

# feature_tag → (command_name, description_ar, admin_only)
_TAG_COMMANDS: dict[str, list[tuple[str, str, bool]]] = {
    "order_management": [
        ("orders", "عرض وإدارة الطلبات", False),
        ("order", "تفاصيل طلب", False),
        ("neworder", "إنشاء طلب جديد", False),
    ],
    "shipping": [
        ("track", "تتبع الشحنة", False),
        ("delivery", "حالة التوصيل", False),
    ],
    "search": [
        ("search", "بحث", False),
    ],
    "admin_panel": [
        ("admin", "لوحة الإدارة", True),
        ("stats", "إحصائيات", True),
    ],
    "notifications": [
        ("notifications", "الإشعارات", False),
    ],
    "ratings": [
        ("rate", "تقييم", False),
    ],
    "crm": [
        ("customers", "العملاء", True),
    ],
    "file_handling": [
        ("files", "الملفات", False),
    ],
    "analytics": [
        ("analytics", "تحليلات", True),
    ],
    "bot_commands": [],
    "welcome_message": [],
    "database": [],
}

# entity name (lower) → commands
_ENTITY_COMMANDS: dict[str, list[tuple[str, str, bool]]] = {
    "order": [("orders", "الطلبات", False), ("order", "طلب", False)],
    "product": [("products", "المنتجات", False), ("catalog", "الكتالوج", False)],
    "user": [("profile", "الملف الشخصي", False)],
    "notification": [("notifications", "الإشعارات", False)],
    "documentjob": [("docs", "المستندات", False)],
    "groupsettings": [("group", "إعدادات المجموعة", True)],
}

_TAG_BUTTONS: dict[str, list[tuple[str, str]]] = {
    "order_management": [("طلباتي", "orders"), ("طلب جديد", "neworder")],
    "shipping": [("تتبع", "track")],
    "search": [("بحث", "search")],
    "admin_panel": [("الإدارة", "admin")],
    "notifications": [("إشعارات", "notifications")],
}


def effective_commands(c: ProgramContract) -> list[CommandUnit]:
    """Merge declared commands with ones derived from tags/entities."""
    by_name: dict[str, CommandUnit] = {}
    for cmd in c.commands:
        by_name[cmd.name] = cmd
    # always ensure start/help
    if "start" not in by_name:
        by_name["start"] = CommandUnit(name="start", description="بدء", admin_only=False)
    if "help" not in by_name:
        by_name["help"] = CommandUnit(name="help", description="المساعدة", admin_only=False)

    tags = {t.lower() for t in (c.feature_tags or [])}
    for tag in tags:
        for name, desc, admin in _TAG_COMMANDS.get(tag, []):
            if name not in by_name:
                by_name[name] = CommandUnit(name=name, description=desc, admin_only=admin)

    for ent in c.entities or []:
        key = ent.name.lower().replace("_", "")
        for name, desc, admin in _ENTITY_COMMANDS.get(key, []):
            if name not in by_name:
                by_name[name] = CommandUnit(name=name, description=desc, admin_only=admin)

    # stable order: start, help, then alpha
    ordered: list[CommandUnit] = []
    for n in ("start", "help"):
        if n in by_name:
            ordered.append(by_name.pop(n))
    ordered.extend(sorted(by_name.values(), key=lambda x: x.name))
    return ordered


def effective_buttons(c: ProgramContract) -> list[ButtonUnit]:
    if c.buttons:
        return list(c.buttons)
    out: list[ButtonUnit] = []
    seen: set[str] = set()
    tags = {t.lower() for t in (c.feature_tags or [])}
    for tag in tags:
        for label, cb in _TAG_BUTTONS.get(tag, []):
            if cb not in seen:
                seen.add(cb)
                out.append(ButtonUnit(label=label, callback_id=cb))
    if not out:
        out.append(ButtonUnit(label="القائمة", callback_id="main_menu"))
    return out[:12]


def effective_services(c: ProgramContract) -> list[ServiceUnit]:
    by_name: dict[str, ServiceUnit] = {s.name: s for s in (c.services or [])}
    tags = {t.lower() for t in (c.feature_tags or [])}
    entity_names = [e.name.lower() for e in (c.entities or [])]

    def add(name: str, resp: str) -> None:
        if name not in by_name:
            by_name[name] = ServiceUnit(name=name, responsibility=resp)

    if "order_management" in tags or any("order" in n for n in entity_names):
        add("orders", "order lifecycle")
    if any("product" in n for n in entity_names):
        add("catalog", "products catalog")
    if "notifications" in tags or any("notification" in n for n in entity_names):
        add("notifications", "user notifications")
    if c.tech.file_handling or "file_handling" in tags:
        add("storage", "file storage")
    if c.tech.database == "postgres" or "postgres" in (c.integrations or []):
        add("persistence", "database access")
    if "users" not in by_name and any("user" in n for n in entity_names):
        add("users", "user accounts")
    if not by_name:
        add("core", "core domain")
    return list(by_name.values())


def welcome_text(c: ProgramContract) -> str:
    """Short professional welcome — never dump raw long summary."""
    tags = {t.lower() for t in (c.feature_tags or [])}
    bits: list[str] = [f"مرحباً بك في {c.bot_name}"]
    if "order_management" in tags or "shipping" in tags:
        bits.append("إدارة الطلبات والتوصيل.")
    elif "ecommerce" in (c.bot_kind.value if c.bot_kind else ""):
        bits.append("تسوق وإدارة الطلبات.")
    else:
        bits.append("استخدم الأوامر أو القائمة للبدء.")
    bits.append("اكتب /help لعرض الأوامر.")
    return "\n".join(bits)


def help_text(commands: list[CommandUnit]) -> str:
    lines = [f"/{c.name} — {c.description or c.name}" for c in commands]
    return "\n".join(lines) if lines else "/start — بدء"
