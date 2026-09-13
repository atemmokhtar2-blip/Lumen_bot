"""Lumen template — professional group moderator.

OWNER_ADMIN_ID is injected by Lumen when the template is materialized for a user.
That Telegram user is always treated as the bot owner/admin (platform owner).
The bot itself must still be promoted to group admin by a group owner.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from telegram import ChatPermissions, Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("lumen.tpl.group_moderator")

# Default offensive / spam patterns (Arabic + Latin). Owner can extend later.
_DEFAULT_BAD = (
    "كس امك",
    "كس أمك",
    "ابن الشرموطة",
    "شرموطة",
    "عرص",
    "منيوك",
    "خول",
    "زب",
    "طيز",
    "fuck",
    "shit",
    "bitch",
    "asshole",
    "nigga",
    "nigger",
)


def _load_owner_id() -> int:
    """Resolve owner admin: env first (runtime inject), then lumen_owner.json."""
    for key in ("OWNER_ADMIN_ID", "LUMEN_OWNER_ID", "LUMEN_OWNER_ADMIN_ID"):
        raw = (os.getenv(key) or "").strip()
        if raw.isdigit():
            return int(raw)
    # Written by Lumen materialize_to_sandbox
    for name in ("lumen_owner.json", ".lumen_owner.json"):
        p = Path(__file__).resolve().parent / name
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            v = data.get("owner_admin_id") or data.get("owner_user_id") or data.get("user_id")
            if v is not None and str(v).strip().isdigit():
                return int(str(v).strip())
        except Exception:
            log.warning("failed reading %s", p)
    return 0


OWNER_ADMIN_ID = _load_owner_id()
WARN_LIMIT = max(1, int(os.getenv("WARN_LIMIT") or "3"))
MUTE_MINUTES_DEFAULT = max(1, int(os.getenv("MUTE_MINUTES") or "60"))

# In-memory warn counters: (chat_id, user_id) -> count
_warns: dict[tuple[int, int], int] = {}


def _bad_patterns() -> list[re.Pattern[str]]:
    extra = (os.getenv("EXTRA_BAD_WORDS") or "").strip()
    words = list(_DEFAULT_BAD)
    if extra:
        words.extend(w.strip() for w in extra.split(",") if w.strip())
    return [re.compile(re.escape(w), re.IGNORECASE) for w in words]


BAD_RE = _bad_patterns()


def _is_owner(user_id: int | None) -> bool:
    return bool(OWNER_ADMIN_ID and user_id and int(user_id) == int(OWNER_ADMIN_ID))


async def _is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if _is_owner(user_id):
        return True
    chat = update.effective_chat
    if chat is None:
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, user_id)
        return member.status in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }
    except Exception:
        return False


def _target_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Resolve target from reply or /cmd <id>."""
    msg = update.effective_message
    if msg and msg.reply_to_message and msg.reply_to_message.from_user:
        return int(msg.reply_to_message.from_user.id)
    if context.args:
        raw = (context.args[0] or "").strip()
        if raw.isdigit():
            return int(raw)
    return None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id if update.effective_user else 0
    owner_note = (
        f"المالك المسجّل من Lumen: `{OWNER_ADMIN_ID}`"
        if OWNER_ADMIN_ID
        else "لم يُحقن OWNER_ADMIN_ID — أعد التشغيل من منصة Lumen."
    )
    you = "أنت المالك/الأدمن التلقائي لهذا البوت." if _is_owner(uid) else "أوامر الإشراف للمالك وأدمن المجموعة فقط."
    text = (
        "🛡️ *مشرف مجموعات Lumen*\n\n"
        f"{owner_note}\n"
        f"{you}\n\n"
        "*الأوامر (رد على رسالة أو ألحق user_id):*\n"
        "• `/ban` — حظر من المجموعة\n"
        "• `/unban <id>` — رفع الحظر\n"
        "• `/mute [دقائق]` — كتم\n"
        "• `/unmute` — فك الكتم\n"
        "• `/warn` — تحذير (بعد الحد → كتم)\n"
        "• `/rules` — القوانين\n"
        "• `/id` — عرض المعرّفات\n\n"
        "⚠️ اجعل البوت *مشرفًا* في المجموعة مع صلاحيات الحظر/التقييد."
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    c = update.effective_chat
    lines = [
        f"your_id: `{u.id if u else '?'}`",
        f"chat_id: `{c.id if c else '?'}`",
        f"OWNER_ADMIN_ID: `{OWNER_ADMIN_ID or '—'}`",
        f"you_are_owner: `{_is_owner(u.id if u else 0)}`",
    ]
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📜 القوانين:\n"
        "1) الاحترام — ممنوع السب والإساءة\n"
        "2) ممنوع السبام والروابط المزعجة\n"
        "3) التزم بتعليمات المشرفين\n"
        "المخالفة → تحذير / كتم / حظر."
    )


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor = update.effective_user.id if update.effective_user else 0
    if not await _is_group_admin(update, context, actor):
        await update.effective_message.reply_text("هذا الأمر للمشرفين فقط.")
        return
    chat = update.effective_chat
    if chat is None or chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await update.effective_message.reply_text("استخدم الأمر داخل مجموعة.")
        return
    tid = _target_user_id(update, context)
    if not tid:
        await update.effective_message.reply_text("رد على رسالة العضو أو: /ban <user_id>")
        return
    if _is_owner(tid):
        await update.effective_message.reply_text("لا يمكن حظر مالك البوت.")
        return
    try:
        await context.bot.ban_chat_member(chat.id, tid)
        await update.effective_message.reply_text(f"تم حظر `{tid}`.", parse_mode="Markdown")
    except Exception as exc:
        await update.effective_message.reply_text(
            f"تعذر الحظر — تأكد أن البوت مشرف بصلاحية الحظر.\n({type(exc).__name__})"
        )


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor = update.effective_user.id if update.effective_user else 0
    if not await _is_group_admin(update, context, actor):
        await update.effective_message.reply_text("هذا الأمر للمشرفين فقط.")
        return
    chat = update.effective_chat
    if chat is None:
        return
    tid = _target_user_id(update, context)
    if not tid:
        await update.effective_message.reply_text("/unban <user_id> أو رد على رسالة.")
        return
    try:
        await context.bot.unban_chat_member(chat.id, tid, only_if_banned=True)
        await update.effective_message.reply_text(f"تم رفع الحظر عن `{tid}`.", parse_mode="Markdown")
    except Exception as exc:
        await update.effective_message.reply_text(f"تعذر رفع الحظر ({type(exc).__name__}).")


async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor = update.effective_user.id if update.effective_user else 0
    if not await _is_group_admin(update, context, actor):
        await update.effective_message.reply_text("هذا الأمر للمشرفين فقط.")
        return
    chat = update.effective_chat
    if chat is None or chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await update.effective_message.reply_text("استخدم الأمر داخل مجموعة.")
        return
    tid = _target_user_id(update, context)
    if not tid:
        await update.effective_message.reply_text("رد على رسالة العضو أو: /mute <user_id> [دقائق]")
        return
    if _is_owner(tid):
        await update.effective_message.reply_text("لا يمكن كتم مالك البوت.")
        return
    minutes = MUTE_MINUTES_DEFAULT
    # /mute 30 when target from reply; /mute <id> 30
    if context.args:
        for a in context.args:
            if a.isdigit() and int(a) != tid:
                minutes = max(1, min(24 * 60, int(a)))
                break
            if a.isdigit() and not update.effective_message.reply_to_message:
                # first id already consumed as tid
                pass
        if len(context.args) >= 2 and context.args[-1].isdigit():
            minutes = max(1, min(24 * 60, int(context.args[-1])))
    until = None
    try:
        import time as _time
        from datetime import datetime, timezone, timedelta

        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    except Exception:
        until = None
    perms = ChatPermissions(can_send_messages=False)
    try:
        await context.bot.restrict_chat_member(
            chat.id, tid, permissions=perms, until_date=until
        )
        await update.effective_message.reply_text(
            f"تم كتم `{tid}` لمدة {minutes} دقيقة.", parse_mode="Markdown"
        )
    except Exception as exc:
        await update.effective_message.reply_text(
            f"تعذر الكتم — امنح البوت صلاحية Restrict.\n({type(exc).__name__})"
        )


async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor = update.effective_user.id if update.effective_user else 0
    if not await _is_group_admin(update, context, actor):
        await update.effective_message.reply_text("هذا الأمر للمشرفين فقط.")
        return
    chat = update.effective_chat
    if chat is None:
        return
    tid = _target_user_id(update, context)
    if not tid:
        await update.effective_message.reply_text("رد على رسالة العضو أو: /unmute <user_id>")
        return
    perms = ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )
    try:
        await context.bot.restrict_chat_member(chat.id, tid, permissions=perms)
        await update.effective_message.reply_text(f"تم فك الكتم عن `{tid}`.", parse_mode="Markdown")
    except Exception as exc:
        await update.effective_message.reply_text(f"تعذر فك الكتم ({type(exc).__name__}).")


async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor = update.effective_user.id if update.effective_user else 0
    if not await _is_group_admin(update, context, actor):
        await update.effective_message.reply_text("هذا الأمر للمشرفين فقط.")
        return
    chat = update.effective_chat
    if chat is None:
        return
    tid = _target_user_id(update, context)
    if not tid:
        await update.effective_message.reply_text("رد على رسالة العضو أو: /warn <user_id>")
        return
    if _is_owner(tid):
        await update.effective_message.reply_text("لا يمكن تحذير مالك البوت.")
        return
    key = (int(chat.id), int(tid))
    _warns[key] = _warns.get(key, 0) + 1
    count = _warns[key]
    await update.effective_message.reply_text(
        f"تحذير `{tid}`: {count}/{WARN_LIMIT}", parse_mode="Markdown"
    )
    if count >= WARN_LIMIT:
        perms = ChatPermissions(can_send_messages=False)
        try:
            await context.bot.restrict_chat_member(chat.id, tid, permissions=perms)
            await update.effective_message.reply_text(
                f"وصل `{tid}` لحد التحذيرات — تم الكتم.", parse_mode="Markdown"
            )
        except Exception as exc:
            await update.effective_message.reply_text(f"تعذر الكتم التلقائي ({type(exc).__name__}).")


async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.new_chat_members:
        return
    for m in msg.new_chat_members:
        if m.is_bot:
            continue
        name = m.full_name or m.username or "عضو"
        await msg.reply_text(
            f"مرحبًا {name} 👋\nالتزم بالقوانين: /rules"
        )


async def on_text_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or not chat:
        return
    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return
    if _is_owner(user.id) or await _is_group_admin(update, context, user.id):
        return
    text = msg.text or msg.caption or ""
    if not text:
        return
    if not any(p.search(text) for p in BAD_RE):
        return
    try:
        await msg.delete()
    except Exception:
        pass
    key = (int(chat.id), int(user.id))
    _warns[key] = _warns.get(key, 0) + 1
    count = _warns[key]
    try:
        await msg.reply_text(
            f"🚫 تم حذف رسالة مسيئة من `{user.id}` (تحذير {count}/{WARN_LIMIT}).",
            parse_mode="Markdown",
        )
    except Exception:
        pass
    if count >= WARN_LIMIT:
        try:
            await context.bot.restrict_chat_member(
                chat.id, user.id, permissions=ChatPermissions(can_send_messages=False)
            )
        except Exception:
            log.warning("auto-mute after bad words failed chat=%s user=%s", chat.id, user.id)


def main() -> None:
    token = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN missing")
    if not OWNER_ADMIN_ID:
        log.warning("OWNER_ADMIN_ID not set — admin commands will only work for Telegram group admins")
    else:
        log.info("OWNER_ADMIN_ID=%s (injected by Lumen)", OWNER_ADMIN_ID)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(CommandHandler("warn", cmd_warn))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_member))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, on_text_filter), group=1)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
