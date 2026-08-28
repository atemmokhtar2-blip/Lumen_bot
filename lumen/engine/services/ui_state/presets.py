"""Bot-type presets for guided generation (engine-owned copy, not UX fluff)."""
from __future__ import annotations

# arg → Arabic label, generation seed (real brief for run_generation)
BOT_TYPE_PRESETS: dict[str, tuple[str, str]] = {
    "shop": (
        "متجر",
        "بوت متجر تيليجرام مع قائمة منتجات وسلة وطلبات وتخزين SQLite "
        "وأوامر /start /help /catalog /cart /order",
    ),
    "notify": (
        "إشعارات",
        "بوت إشعارات تيليجرام للاشتراك وإرسال رسائل للمستخدمين مع SQLite "
        "وأوامر /start /help /subscribe /broadcast",
    ),
    "tasks": (
        "مهام",
        "بوت إدارة مهام تيليجرام لإضافة وإكمال وعرض المهام مع SQLite "
        "وأوامر /start /help /add /list /done",
    ),
    "chat": (
        "محادثة",
        "بوت محادثة تيليجرام بسيط مع ردود جاهزة وأوامر /start /help",
    ),
    "custom": (
        "مخصص",
        "",  # user must type
    ),
}


def preset_description(type_id: str) -> str:
    row = BOT_TYPE_PRESETS.get((type_id or "").strip().lower())
    return row[1] if row else ""


def preset_label(type_id: str) -> str:
    row = BOT_TYPE_PRESETS.get((type_id or "").strip().lower())
    return row[0] if row else type_id
