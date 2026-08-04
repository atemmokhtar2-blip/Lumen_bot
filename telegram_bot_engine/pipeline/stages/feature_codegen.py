"""
Feature-aware code generation for materialize stage.

Turns analysis/blueprint features into real python-telegram-bot handlers
instead of a generic Hello World main.py.
"""

from __future__ import annotations

from typing import Any, List, Optional, Set


def collect_features(context: Any) -> List[str]:
    names: List[str] = []
    if context is None:
        return names

    report = context.get("analysis_report") if hasattr(context, "get") else None
    if report is not None:
        for f in getattr(report, "features", []) or []:
            n = getattr(f, "name", None) or str(f)
            if n:
                names.append(str(n).lower())

    bp = context.get("project_blueprint") if hasattr(context, "get") else None
    if bp is not None:
        for f in getattr(bp, "features", []) or []:
            n = getattr(f, "name", None) or str(f)
            if n:
                names.append(str(n).lower())

    req = (getattr(context, "request", "") or "").lower()
    keyword_map = {
        "ban": ["ban", "/ban", "حظر", "طرد"],
        "mute": ["mute", "/mute", "كتم"],
        "warn": ["warn", "/warn", "تحذير"],
        "stats": ["stats", "/stats", "إحصائ", "احصائ"],
        "welcome": ["welcome", "ترحيب", "أعضاء جدد", "اعضاء جدد", "new member"],
        "user_management": ["user_management", "مستخدمين", "أعضاء", "اعضاء"],
        "admin_panel": ["admin", "مشرف", "إدارة مجموعات", "ادارة مجموعات", "group admin"],
        "message_handler": ["بيرد", "يرد", "reply", "echo"],
    }
    for feat, kws in keyword_map.items():
        if any(k in req for k in kws):
            names.append(feat)

    out: List[str] = []
    seen: Set[str] = set()
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def resolve_start_reply(request: str, features: List[str], fallback: str = "Hello World") -> str:
    text = request or ""
    # Explicit quoted reply after /start
    import re
    m = re.search(r"""/start[^\"'\n]{0,80}[\"']([^\"']+)[\"']""", text, re.I | re.S)
    if m:
        return m.group(1).strip() or fallback
    m = re.search(
        r"""(?:يرسل|send|replies?|reply)\s*[:：]?\s*[\"']?([^\n\"']+)[\"']?""",
        text,
        re.I,
    )
    if m:
        c = m.group(1).strip().strip("-•* ")
        if c and len(c) < 120 and "/start" not in c.lower():
            # avoid capturing feature lists
            if not any(x in c for x in ("/ban", "/mute", "أمر", "مميزات")):
                return c
    if re.search(r"hello\s*world", text, re.I):
        return "Hello World"
    if "هاي" in text and not features:
        return "هاي"

    admin_feats = {"ban", "mute", "warn", "stats", "welcome", "admin_panel", "user_management"}
    if admin_feats.intersection(features):
        return (
            "مرحباً أيها المشرف 👋\n"
            "أوامر الإدارة:\n"
            "/ban — حظر عضو\n"
            "/mute — كتم عضو\n"
            "/warn — تحذير\n"
            "/stats — إحصائيات\n"
            "/help — المساعدة"
        )
    return fallback


def build_ptb_main(start_reply: str, features: List[str]) -> str:
    feats = set(features)
    reply = repr(start_reply)

    has_ban = "ban" in feats or any("ban" in f for f in feats)
    has_mute = "mute" in feats or any("mute" in f for f in feats)
    has_warn = "warn" in feats or any("warn" in f for f in feats)
    has_stats = (
        "stats" in feats
        or "analytics" in feats
        or any("stat" in f or "analytics" in f for f in feats)
    )
    has_welcome = "welcome" in feats or any("welcome" in f for f in feats)

    help_lines = ["الأوامر:", "/start", "/help"]
    extra_blocks: List[str] = []
    register: List[str] = [
        '    app.add_handler(CommandHandler("start", start))',
        '    app.add_handler(CommandHandler("help", help_cmd))',
    ]

    if has_ban:
        help_lines.append("/ban — حظر عضو (رد على رسالة)")
        register.append('    app.add_handler(CommandHandler("ban", ban))')
        extra_blocks.append(
            '''
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("هذا الأمر للمجموعات فقط.")
        return
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("هذا الأمر للمشرفين فقط.")
        return
    target = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            target = int(context.args[0])
        except ValueError:
            await update.message.reply_text("استخدم: /ban بالرد على رسالة أو /ban <user_id>")
            return
    if not target:
        await update.message.reply_text("حدد العضو أولاً.")
        return
    await context.bot.ban_chat_member(chat.id, target)
    await update.message.reply_text(f"تم حظر العضو {target}.")
'''
        )

    if has_mute:
        help_lines.append("/mute [دقائق] — كتم عضو")
        register.append('    app.add_handler(CommandHandler("mute", mute))')
        extra_blocks.append(
            '''
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from datetime import datetime, timedelta, timezone
    from telegram import ChatPermissions
    if not update.message or not update.effective_chat:
        return
    chat = update.effective_chat
    user = update.effective_user
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("للمشرفين فقط.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        await update.message.reply_text("رد على رسالة العضو ثم: /mute [دقائق]")
        return
    target = update.message.reply_to_message.from_user.id
    minutes = 60
    if context.args:
        try:
            minutes = int(context.args[0])
        except ValueError:
            pass
    until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    await context.bot.restrict_chat_member(
        chat.id,
        target,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until,
    )
    await update.message.reply_text(f"تم كتم {target} لمدة {minutes} دقيقة.")
'''
        )

    if has_warn:
        help_lines.append("/warn — تحذير عضو")
        register.append('    app.add_handler(CommandHandler("warn", warn))')
        extra_blocks.append(
            '''
_WARNINGS = {}

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat = update.effective_chat
    user = update.effective_user
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("للمشرفين فقط.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        await update.message.reply_text("رد على رسالة العضو لاستخدام /warn")
        return
    target = update.message.reply_to_message.from_user
    key = (chat.id, target.id)
    _WARNINGS[key] = _WARNINGS.get(key, 0) + 1
    count = _WARNINGS[key]
    await update.message.reply_text(f"تحذير لـ {target.full_name}. العدد: {count}")
    if count >= 3:
        await context.bot.ban_chat_member(chat.id, target.id)
        await update.message.reply_text("3 تحذيرات — تم الحظر.")
'''
        )

    if has_stats:
        help_lines.append("/stats — إحصائيات المجموعة")
        register.append('    app.add_handler(CommandHandler("stats", stats))')
        extra_blocks.append(
            '''
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat = update.effective_chat
    try:
        count = await context.bot.get_chat_member_count(chat.id)
    except Exception:
        count = "?"
    await update.message.reply_text(
        f"إحصائيات المجموعة:\\n• الاسم: {chat.title or chat.id}\\n• الأعضاء: {count}"
    )
'''
        )

    if has_welcome:
        register.append(
            "    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))"
        )
        extra_blocks.append(
            '''
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.new_chat_members:
        return
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        await update.message.reply_text(
            f"أهلاً {member.full_name} في المجموعة! التزم بالقوانين."
        )
'''
        )

    help_text = repr("\n".join(help_lines))
    extras = "\n".join(extra_blocks)
    regs = "\n".join(register)

    return f'''"""Telegram bot entry point (python-telegram-bot) — feature-aware generation."""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in the environment or .env file.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text({reply})


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text({help_text})

{extras}

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
{regs}
    logger.info("Starting bot (polling) features={list(feats)!r}")
    app.run_polling()


if __name__ == "__main__":
    main()
'''


def build_feature_module(stem: str) -> Optional[str]:
    """Optional richer module body for package feature files."""
    s = stem.lower().replace("-", "_")
    if "ban" in s:
        return '''"""Ban moderation helpers."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def ban_user(bot, chat_id: int, user_id: int) -> None:
    await bot.ban_chat_member(chat_id, user_id)
'''
    if "mute" in s:
        return '''"""Mute helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram import ChatPermissions


async def mute_user(bot, chat_id: int, user_id: int, minutes: int = 60) -> None:
    until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    await bot.restrict_chat_member(
        chat_id,
        user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until,
    )
'''
    if "warn" in s:
        return '''"""Warn counter helpers."""
from __future__ import annotations

_WARNINGS = {}


def add_warning(chat_id: int, user_id: int) -> int:
    key = (chat_id, user_id)
    _WARNINGS[key] = _WARNINGS.get(key, 0) + 1
    return _WARNINGS[key]
'''
    if "welcome" in s:
        return '''"""Welcome message helper."""
from __future__ import annotations


def welcome_text(name: str) -> str:
    return f"أهلاً {name} في المجموعة! التزم بالقوانين."
'''
    if "stat" in s or "analytics" in s:
        return '''"""Stats helper."""
from __future__ import annotations


def format_stats(title: str, count) -> str:
    return f"إحصائيات:\\n• {title}\\n• أعضاء: {count}"
'''
    return None
