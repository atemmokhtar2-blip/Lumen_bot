"""
World-class Data Model Knowledge Base.

Maps domain language → precise entity schemas the engine must materialize.
Used by understanding to fill FormalBotSpec.data_models completely.
"""

from __future__ import annotations

from typing import Any

# Canonical field types for clean codegen
FieldDef = dict[str, str]  # name -> python type hint

# ── Core reusable entities ────────────────────────────────────────────────

ENTITY_LIBRARY: dict[str, list[tuple[str, str]]] = {
    "User": [
        ("id", "int"),
        ("telegram_id", "int"),
        ("username", "str | None"),
        ("full_name", "str"),
        ("phone", "str | None"),
        ("language", "str"),
        ("is_admin", "bool"),
        ("created_at", "str"),
    ],
    "Product": [
        ("id", "str"),
        ("name", "str"),
        ("description", "str"),
        ("price", "int"),
        ("currency", "str"),
        ("stock", "int"),
        ("category", "str"),
        ("image_url", "str | None"),
        ("active", "bool"),
    ],
    "CartItem": [
        ("user_id", "int"),
        ("product_id", "str"),
        ("name", "str"),
        ("price", "int"),
        ("qty", "int"),
    ],
    "Order": [
        ("id", "str"),
        ("user_id", "int"),
        ("items", "list[dict]"),
        ("total", "int"),
        ("status", "str"),
        ("address", "str | None"),
        ("phone", "str | None"),
        ("payment_method", "str | None"),
        ("created_at", "str"),
    ],
    "Ticket": [
        ("id", "str"),
        ("user_id", "int"),
        ("subject", "str"),
        ("body", "str"),
        ("status", "str"),
        ("priority", "str"),
        ("assignee_id", "int | None"),
        ("created_at", "str"),
        ("updated_at", "str"),
    ],
    "TicketMessage": [
        ("id", "str"),
        ("ticket_id", "str"),
        ("sender_id", "int"),
        ("text", "str"),
        ("created_at", "str"),
    ],
    "GroupSettings": [
        ("chat_id", "int"),
        ("welcome_text", "str"),
        ("rules_text", "str"),
        ("mute_duration_sec", "int"),
        ("anti_spam", "bool"),
    ],
    "ModAction": [
        ("id", "str"),
        ("chat_id", "int"),
        ("user_id", "int"),
        ("action", "str"),
        ("by_admin_id", "int"),
        ("reason", "str"),
        ("created_at", "str"),
    ],
    "DocumentJob": [
        ("id", "str"),
        ("user_id", "int"),
        ("status", "str"),
        ("input_text", "str"),
        ("doc_type", "str"),
        ("output_path", "str | None"),
        ("created_at", "str"),
    ],
    "Subscriber": [
        ("user_id", "int"),
        ("active", "bool"),
        ("joined_at", "str"),
    ],
    "Broadcast": [
        ("id", "str"),
        ("text", "str"),
        ("sent_count", "int"),
        ("failed_count", "int"),
        ("created_at", "str"),
    ],
    "Player": [
        ("user_id", "int"),
        ("score", "int"),
        ("level", "int"),
        ("username", "str"),
    ],
    "GameSession": [
        ("id", "str"),
        ("user_id", "int"),
        ("state", "str"),
        ("score", "int"),
        ("payload", "dict"),
    ],
    "Conversation": [
        ("user_id", "int"),
        ("messages", "list[dict]"),
        ("updated_at", "str"),
    ],
    "Payment": [
        ("id", "str"),
        ("order_id", "str"),
        ("user_id", "int"),
        ("amount", "int"),
        ("method", "str"),
        ("status", "str"),
        ("provider_ref", "str | None"),
        ("created_at", "str"),
    ],
    "Notification": [
        ("id", "str"),
        ("user_id", "int"),
        ("title", "str"),
        ("body", "str"),
        ("read", "bool"),
        ("created_at", "str"),
    ],
}

# Domain → required entities
# DOMAIN_ENTITIES removed — entities come from text signals only

# Phrase → entity hints (for free-form long text)
ENTITY_SIGNALS: list[tuple[list[str], str]] = [
    (["منتج", "product", "كتالوج", "catalog", "سعر", "price"], "Product"),
    (["سلة", "cart"], "CartItem"),
    (["طلب", "order", "checkout"], "Order"),
    (["دفع", "payment", "stripe", "فوري"], "Payment"),
    (["تذكرة", "ticket", "شكوى", "تذاكر", "فتح تذكرة"], "Ticket"),
    (["رسالة تذكرة", "ticket message", "رد على تذكرة"], "TicketMessage"),
    (["ترحيب", "welcome", "قواعد المجموعة", "group settings"], "GroupSettings"),
    (["حظر", "ban", "كتم", "mute", "طرد"], "ModAction"),
    (["pdf", "مستند", "document job", "ملف"], "DocumentJob"),
    (["مشترك", "subscriber", "اشتراك"], "Subscriber"),
    (["بث", "broadcast", "إعلان"], "Broadcast"),
    (["نقاط", "score", "لاعب", "player", "مستوى"], "Player"),
    (["جلسة لعبة", "game session"], "GameSession"),
    (["محادثة", "conversation", "سياق"], "Conversation"),
    (["إشعار", "notification", "تنبيه"], "Notification"),
    (["مستخدم", "user", "عميل", "customer"], "User"),
]


def resolve_data_models(archetype: str, text: str) -> list[dict[str, Any]]:
    """Return models grounded in TEXT signals only — never archetype packs."""
    needed: list[str] = []
    t = text.lower()
    full = text or ""

    # Meta / bot-builder contexts: do NOT inject commerce entities from example words
    is_meta = any(
        s in full or s in t
        for s in (
            "بناء بوت", "بناء بوتات", "بوت بناء", "صانع بوتات", "مولد بوتات",
            "bot builder", "bot generator", "create bots", "build bots",
            "meta bot", "meta-bot", "بوت يبني", "يبني بوتات", "انشاء بوتات",
            "إنشاء بوتات", "generate bot", "bot factory", "ai agent", "محرك بوتات",
        )
    )
    commerce_entities = {"Product", "CartItem", "Order", "Payment"}

    for phrases, entity in ENTITY_SIGNALS:
        if any(p.lower() in t for p in phrases) and entity not in needed:
            if is_meta and entity in commerce_entities:
                # only keep if the entity is explicitly requested as a data model
                explicit = (
                    f"كيان {entity}" in full
                    or f"نموذج {entity}" in full
                    or f"model {entity.lower()}" in t
                    or f"entity {entity.lower()}" in t
                    or f"جدول {entity}" in full
                )
                if not explicit:
                    continue
            needed.append(entity)
    # User only if text mentions users / accounts / telegram ids
    if "User" not in needed and any(
        k in t for k in ("مستخدم", "user", "حساب", "telegram", "عميل", "customer")
    ):
        needed.insert(0, "User")

    # Fields: minimal structural set + only library fields whose name/hint appears in text.
    # Never dump full domain entity packs blindly.
    tlow = text.lower()
    field_hints = {
        "address": ("عنوان", "address", "موقع"),
        "phone": ("هاتف", "phone", "جوال", "رقم"),
        "status": ("حالة", "status"),
        "total": ("إجمالي", "total", "سعر"),
        "items": ("منتجات", "items", "سلع"),
        "payment_method": ("دفع", "payment"),
        "subject": ("موضوع", "subject"),
        "body": ("وصف", "body", "محتوى"),
        "priority": ("أولوية", "priority"),
        "slot": ("موعد", "slot", "وقت"),
        "name": ("اسم", "name"),
        "price": ("سعر", "price"),
        "stock": ("مخزون", "stock"),
        "full_name": ("اسم", "full_name"),
        "username": ("username", "مستخدم"),
        "qty": ("كمية", "qty"),
        "description": ("وصف", "description"),
    }
    models = []
    for name in needed:
        lib = ENTITY_LIBRARY.get(name) or [("id", "str")]
        chosen: list[tuple[str, str]] = []
        # always id
        for n, ty in lib:
            if n == "id" and (n, ty) not in chosen:
                chosen.append((n, ty))
        if name == "User":
            for n, ty in lib:
                if n in ("telegram_id", "full_name", "username") and (n, ty) not in chosen:
                    chosen.append((n, ty))
        else:
            # user_id if present in lib
            for n, ty in lib:
                if n == "user_id" and (n, ty) not in chosen:
                    chosen.append((n, ty))
            for n, ty in lib:
                if n in ("id", "user_id", "created_at", "updated_at"):
                    continue
                hints = field_hints.get(n, (n, n.replace("_", " ")))
                if any(h.lower() in tlow or h in text for h in hints):
                    if (n, ty) not in chosen:
                        chosen.append((n, ty))
        if len(chosen) <= 1 and name != "User":
            # at least id + user_id structural
            if not any(n == "user_id" for n, _ in chosen):
                chosen.append(("user_id", "int"))
        models.append({
            "name": name,
            "fields": [{"name": n, "type": ty} for n, ty in chosen],
            "field_names": [n for n, _ in chosen],
        })
    return models
