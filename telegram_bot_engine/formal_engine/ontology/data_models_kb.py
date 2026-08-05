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
    (["تذكرة", "ticket", "شكوى", "دعم"], "Ticket"),
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
    for phrases, entity in ENTITY_SIGNALS:
        if any(p.lower() in t for p in phrases) and entity not in needed:
            needed.append(entity)
    # User only if text mentions users / accounts / telegram ids
    if "User" not in needed and any(
        k in t for k in ("مستخدم", "user", "حساب", "telegram", "عميل", "customer")
    ):
        needed.insert(0, "User")

    models = []
    for name in needed:
        fields = ENTITY_LIBRARY.get(name)
        if not fields:
            fields = [("id", "str"), ("created_at", "str")]
        models.append({
            "name": name,
            "fields": [{"name": n, "type": ty} for n, ty in fields],
            "field_names": [n for n, _ in fields],
        })
    return models
