"""Emit service modules for generated bots (split package)."""
from __future__ import annotations

from ..schema import BotSpec

def _emit_content(spec: BotSpec) -> str:
    rules = "التزم بالاحترام. ممنوع السبام والإعلانات." if (spec.bot.language or "ar").startswith("ar") else "Be respectful. No spam."
    about = spec.bot.description or spec.bot.name
    return (
        '"""Static content helpers."""\n'
        "from __future__ import annotations\n\n"
        f"RULES_TEXT = {rules!r}\n"
        f"ABOUT_TEXT = {about!r}\n\n"
        "def rules() -> str:\n"
        "    return RULES_TEXT\n\n"
        "def about() -> str:\n"
        "    return ABOUT_TEXT\n\n"
        "def faq() -> str:\n"
        "    return (\n"
        '        "الأسئلة الشائعة:\\n"\n'
        '        "- /start للبداية\\n"\n'
        '        "- /help للأوامر\\n"\n'
        '        "- للمساعدة تواصل مع المشرف"\n'
        "    )\n"
    )




def _emit_welcome() -> str:
    return (
        '"""Welcome service — per-chat auto-welcome for new members."""\n'
        "from __future__ import annotations\n\n"
        "from app.db import connect, init_db\n\n"
        'DEFAULT_MESSAGE = "أهلاً {name} 👋 نورت المجموعة!"\n\n'
        "def ensure() -> None:\n"
        "    init_db()\n\n"
        "def set_message(chat_id: int, message: str) -> None:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        conn.execute(\n"
        '            """\n'
        "            INSERT INTO welcome_settings (chat_id, enabled, message) VALUES (?, 1, ?)\n"
        "            ON CONFLICT(chat_id) DO UPDATE SET message = excluded.message, enabled = 1\n"
        '            """,\n'
        "            (chat_id, message),\n"
        "        )\n"
        "        conn.commit()\n\n"
        "def toggle(chat_id: int) -> bool:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        row = conn.execute(\n"
        '            "SELECT enabled FROM welcome_settings WHERE chat_id = ?", (chat_id,)\n'
        "        ).fetchone()\n"
        "        if row is None:\n"
        "            conn.execute(\n"
        '                "INSERT INTO welcome_settings (chat_id, enabled, message) VALUES (?, 1, ?)",\n'
        "                (chat_id, DEFAULT_MESSAGE),\n"
        "            )\n"
        "            conn.commit()\n"
        "            return True\n"
        "        new_val = 0 if int(row['enabled']) else 1\n"
        "        conn.execute(\n"
        '            "UPDATE welcome_settings SET enabled = ? WHERE chat_id = ?",\n'
        "            (new_val, chat_id),\n"
        "        )\n"
        "        conn.commit()\n"
        "        return bool(new_val)\n\n"
        "def get_settings(chat_id: int) -> dict:\n"
        "    ensure()\n"
        "    with connect() as conn:\n"
        "        row = conn.execute(\n"
        '            "SELECT enabled, message FROM welcome_settings WHERE chat_id = ?",\n'
        "            (chat_id,),\n"
        "        ).fetchone()\n"
        "    if row is None:\n"
        '        return {"enabled": True, "message": DEFAULT_MESSAGE}\n'
        "    return {\n"
        "        'enabled': bool(int(row['enabled'])),\n"
        "        'message': row['message'] or DEFAULT_MESSAGE,\n"
        "    }\n\n"
        "def format_welcome(chat_id: int, name: str) -> str | None:\n"
        "    cfg = get_settings(chat_id)\n"
        "    if not cfg['enabled']:\n"
        "        return None\n"
        "    msg = cfg['message'] or DEFAULT_MESSAGE\n"
        "    return msg.replace('{name}', name).replace('{NAME}', name)\n"
    )



