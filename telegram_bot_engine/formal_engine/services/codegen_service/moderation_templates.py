"""Templates for group-moderation command handlers (static-safe real PTB code)."""

from __future__ import annotations


def moderation_handler_source(name: str, description: str) -> str:
    """Return full Python source for a moderation command handler module."""
    fn = f"{name}_handler"
    # Use format carefully — no f-string for outer; only replacements
    tpl = r'''"""Command /__NAME__ — group moderation (ProgramContract)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram import ChatPermissions, Update
from telegram.ext import ContextTypes


async def __FN__(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if message is None or chat is None or user is None:
        return
    if chat.type not in ("group", "supergroup"):
        await message.reply_text("هذا الأمر يعمل داخل المجموعات فقط.")
        return
    member = await context.bot.get_chat_member(chat.id, user.id)
    status = getattr(member, "status", "") or ""
    if status not in ("administrator", "creator"):
        await message.reply_text("هذا الأمر للمشرفين فقط.")
        return

    target = message.reply_to_message.from_user if message.reply_to_message else None
    target_id = target.id if target else None
    if target_id is None and context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            target_id = None
    reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else ""

    if __NAME__ in ("ban", "kick", "mute", "warn", "unban", "unmute") and target_id is None:
        await message.reply_text(
            "استخدم /__NAME__ بالرد على رسالة العضو أو: /__NAME__ <user_id> [سبب]"
        )
        return

    try:
        if __NAME__ == "ban" and target_id is not None:
            await context.bot.ban_chat_member(chat.id, target_id)
            await message.reply_text(f"تم حظر المستخدم {target_id}. {reason}".strip())
        elif __NAME__ == "unban" and target_id is not None:
            await context.bot.unban_chat_member(chat.id, target_id)
            await message.reply_text(f"تم فك الحظر عن {target_id}.")
        elif __NAME__ == "kick" and target_id is not None:
            await context.bot.ban_chat_member(chat.id, target_id)
            await context.bot.unban_chat_member(chat.id, target_id)
            await message.reply_text(f"تم طرد المستخدم {target_id}.")
        elif __NAME__ == "mute" and target_id is not None:
            until = datetime.now(timezone.utc) + timedelta(hours=1)
            await context.bot.restrict_chat_member(
                chat.id,
                target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            await message.reply_text(f"تم كتم {target_id} لمدة ساعة.")
        elif __NAME__ == "unmute" and target_id is not None:
            await context.bot.restrict_chat_member(
                chat.id,
                target_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ),
            )
            await message.reply_text(f"تم فك الكتم عن {target_id}.")
        elif __NAME__ == "warn" and target_id is not None:
            await message.reply_text(
                f"تحذير للمستخدم {target_id}. {reason or __DESC__}".strip()
            )
        elif __NAME__ == "setwelcome":
            text = " ".join(context.args) if context.args else ""
            if not text:
                await message.reply_text("الاستخدام: /setwelcome نص الترحيب")
                return
            context.application.bot_data.setdefault("welcome", {})[chat.id] = text
            await message.reply_text("تم حفظ رسالة الترحيب لهذه المجموعة.")
        else:
            await message.reply_text("/__NAME__: __DESC__")
    except Exception as exc:
        await message.reply_text(f"تعذر تنفيذ /__NAME__: {type(exc).__name__}")
'''
    return (
        tpl.replace("__NAME__", name)
        .replace("__FN__", fn)
        .replace("__DESC__", description.replace('"', "'")[:80])
    )


MOD_COMMANDS = frozenset({"ban", "unban", "kick", "mute", "unmute", "warn", "setwelcome"})
