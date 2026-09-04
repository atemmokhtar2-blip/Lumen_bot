"""Telegram UI for multi-conversation threads (WhatsApp-style)."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _kb_conversations(rows: list[Any]) -> Any:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    buttons = []
    for c in rows[:12]:
        title = (getattr(c, "title", None) or "محادثة")[:40]
        cid = getattr(c, "id", "")
        buttons.append([InlineKeyboardButton(f"💬 {title}", callback_data=f"conv:select:{cid}")])
    buttons.append([InlineKeyboardButton("➕ محادثة جديدة", callback_data="conv:new")])
    return InlineKeyboardMarkup(buttons)


async def cmd_new_conversation(update, context) -> None:
    """ /new — start a fresh conversation thread."""
    user = update.effective_user
    if not user:
        return
    uid = int(user.id)
    try:
        from lumen.platform.conversations import get_conversation_service
        from lumen.bot.session_store import get_session_store

        get_session_store().hydrate(uid, context.user_data)
        conv = get_conversation_service().new_conversation(uid)
        context.user_data["current_conversation_id"] = conv.id
        get_session_store().save(uid, dict(context.user_data or {}))
        await update.effective_message.reply_text(
            f"✅ محادثة جديدة\nالعنوان: {conv.title}\nالمعرّف: `{conv.id[:12]}…`\n\n"
            "اكتب رسالتك — السياق هيبدأ من هنا.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("cmd_new_conversation")
        await update.effective_message.reply_text(f"تعذر إنشاء محادثة: {type(exc).__name__}")


async def cmd_conversations(update, context) -> None:
    """ /conversations — list and pick a thread."""
    user = update.effective_user
    if not user:
        return
    uid = int(user.id)
    try:
        from lumen.platform.conversations import get_conversation_service
        from lumen.bot.session_store import get_session_store

        get_session_store().hydrate(uid, context.user_data)
        rows = get_conversation_service().list_for_user(uid, limit=12)
        if not rows:
            await update.effective_message.reply_text(
                "مافيش محادثات بعد. اكتب /new أو أرسل رسالة لبدء محادثة."
            )
            return
        current = str(context.user_data.get("current_conversation_id") or "")
        lines = ["محادثاتك:"]
        for c in rows:
            mark = "▶️" if c.id == current else "•"
            lines.append(f"{mark} {c.title} ({c.message_count} رسالة)")
        await update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=_kb_conversations(rows),
        )
    except Exception as exc:
        logger.exception("cmd_conversations")
        await update.effective_message.reply_text(f"تعذر جلب المحادثات: {type(exc).__name__}")


async def cmd_history(update, context) -> None:
    """ /history — show recent messages in the active conversation."""
    user = update.effective_user
    if not user:
        return
    uid = int(user.id)
    try:
        from lumen.platform.conversations import get_conversation_service
        from lumen.bot.session_store import get_session_store

        get_session_store().hydrate(uid, context.user_data)
        svc = get_conversation_service()
        cid = str(context.user_data.get("current_conversation_id") or "")
        conv = svc.ensure_active(uid, conversation_id=cid or None)
        context.user_data["current_conversation_id"] = conv.id
        ctx = svc.context_for_llm(uid, conv.id)
        lines = [f"📜 {conv.title}", f"الملخص: {(ctx.get('summary') or '—')[:200]}", ""]
        for m in (ctx.get("messages") or [])[-15:]:
            role = "أنت" if m.get("role") == "user" else "البوت"
            lines.append(f"{role}: {(m.get('content') or '')[:200]}")
        text = "\n".join(lines)
        if len(text) > 3500:
            text = text[:3500] + "…"
        await update.effective_message.reply_text(text)
    except Exception as exc:
        logger.exception("cmd_history")
        await update.effective_message.reply_text(f"تعذر عرض السجل: {type(exc).__name__}")


async def handle_conversation_callback(update, context) -> bool:
    try:
        u = getattr(update, "effective_user", None)
        if u is not None:
            from lumen.bot.referral_hooks import qualify_bot_use
            await qualify_bot_use(context, int(u.id), "command_non_start")
    except Exception:
        pass

    """Handle conv:select:ID and conv:new. Returns True if handled."""
    q = update.callback_query
    if not q or not q.data:
        return False
    data = str(q.data)
    if not data.startswith("conv:"):
        return False
    user = update.effective_user
    if not user:
        return False
    uid = int(user.id)
    try:
        from lumen.platform.conversations import get_conversation_service
        from lumen.bot.session_store import get_session_store

        get_session_store().hydrate(uid, context.user_data)
        svc = get_conversation_service()
        if data == "conv:new":
            conv = svc.new_conversation(uid)
            context.user_data["current_conversation_id"] = conv.id
            get_session_store().save(uid, dict(context.user_data or {}))
            await q.answer("محادثة جديدة")
            await q.edit_message_text(f"✅ محادثة جديدة: {conv.title}")
            return True
        if data.startswith("conv:select:"):
            cid = data.split(":", 2)[-1]
            conv = svc.ensure_active(uid, conversation_id=cid)
            if conv.id != cid:
                await q.answer("محادثة غير موجودة", show_alert=True)
                return True
            context.user_data["current_conversation_id"] = conv.id
            try:
                svc._store.touch_conversation(conv.id)
            except Exception:
                pass
            get_session_store().save(uid, dict(context.user_data or {}))
            await q.answer("تم التحديد")
            await q.edit_message_text(f"▶️ المحادثة النشطة: {conv.title}")
            return True
    except Exception:
        logger.exception("conversation callback")
        try:
            await q.answer("خطأ", show_alert=True)
        except Exception:
            pass
        return True
    return False


def apply_start_deep_link(context, user_id: int, payload: str) -> str | None:
    """If /start conversation_<id> — activate that thread. Returns notice text or None."""
    raw = (payload or "").strip()
    if not raw.startswith("conversation_"):
        return None
    cid = raw[len("conversation_") :].strip()
    if not cid:
        return None
    try:
        from lumen.platform.conversations import get_conversation_service
        from lumen.bot.session_store import get_session_store

        conv = get_conversation_service().ensure_active(int(user_id), conversation_id=cid)
        if conv.id != cid:
            return "المحادثة غير موجودة أو ليست لك."
        context.user_data["current_conversation_id"] = conv.id
        get_session_store().save(int(user_id), dict(context.user_data or {}))
        return f"تم فتح المحادثة: {conv.title}"
    except Exception as exc:
        logger.debug("deep link conversation failed: %s", type(exc).__name__)
        return None


def resolve_active_conversation_id(user_id: int, user_data: dict | None) -> str:
    """Prefer session current_conversation_id; else last active; else create."""
    from lumen.platform.conversations import get_conversation_service
    from lumen.bot.session_store import get_session_store

    uid = int(user_id)
    ud = user_data if isinstance(user_data, dict) else {}
    cid = str(ud.get("current_conversation_id") or "").strip()
    svc = get_conversation_service()
    conv = svc.ensure_active(uid, conversation_id=cid or None)
    ud["current_conversation_id"] = conv.id
    try:
        get_session_store().save(uid, dict(ud))
    except Exception:
        logger.debug("session save conversation_id soft-fail", exc_info=True)
    return conv.id


def record_user_and_assistant(

    user_id: int,
    user_data: dict,
    *,
    user_text: str,
    assistant_text: str = "",
) -> str:
    """Append turns to active conversation; return conversation_id."""
    from lumen.platform.conversations import get_conversation_service
    from lumen.bot.session_store import get_session_store

    uid = int(user_id)
    svc = get_conversation_service()
    if not isinstance(user_data, dict):
        user_data = {}
    cid = resolve_active_conversation_id(uid, user_data)
    conv = svc.ensure_active(uid, conversation_id=cid)
    user_data["current_conversation_id"] = conv.id
    if user_text:
        svc.append(uid, conv.id, role="user", content=user_text)
    if assistant_text:
        svc.append(uid, conv.id, role="assistant", content=assistant_text)
    try:
        get_session_store().save(uid, dict(user_data or {}))
    except Exception:
        pass
    return conv.id


def llm_context_block(user_id: int, user_data: dict) -> str:
    """Text block injected into agent/engine prompts."""
    from lumen.platform.conversations import get_conversation_service

    uid = int(user_id)
    svc = get_conversation_service()
    if not isinstance(user_data, dict):
        user_data = {}
    cid = resolve_active_conversation_id(uid, user_data)
    conv = svc.ensure_active(uid, conversation_id=cid)
    user_data["current_conversation_id"] = conv.id
    ctx = svc.context_for_llm(uid, conv.id)
    lines = [f"[CONVERSATION id={conv.id} title={conv.title}]"]
    if ctx.get("summary"):
        lines.append(f"[SUMMARY] {ctx['summary'][:1500]}")
    for m in ctx.get("messages") or []:
        lines.append(f"{m.get('role', 'user').upper()}: {m.get('content', '')[:800]}")
    return "\n".join(lines)


async def cmd_export(update, context) -> None:
    """ /export — export active conversation as JSON text."""
    user = update.effective_user
    if not user:
        return
    uid = int(user.id)
    try:
        from lumen.platform.conversations import get_conversation_service
        from lumen.bot.session_store import get_session_store
        get_session_store().hydrate(uid, context.user_data)
        svc = get_conversation_service()
        cid = str(context.user_data.get("current_conversation_id") or "")
        conv = svc.ensure_active(uid, conversation_id=cid or None)
        data = svc.export_json(uid, conv.id)
        import json
        blob = json.dumps(data, ensure_ascii=False, indent=2)
        if len(blob) > 3500:
            blob = blob[:3500] + "\n…(truncated)"
        await update.effective_message.reply_text(f"```json\n{blob}\n```", parse_mode="Markdown")
    except Exception as exc:
        logger.exception("cmd_export")
        await update.effective_message.reply_text(f"تعذر التصدير: {type(exc).__name__}")


async def cmd_search(update, context) -> None:
    """ /search <query> — search across user conversations."""
    user = update.effective_user
    if not user:
        return
    uid = int(user.id)
    q = " ".join(context.args or []).strip()
    if not q:
        await update.effective_message.reply_text("استخدم: /search كلمة البحث")
        return
    try:
        from lumen.platform.conversations import get_conversation_service
        hits = get_conversation_service().search(uid, q, limit=15)
        if not hits:
            await update.effective_message.reply_text("مفيش نتائج.")
            return
        lines = [f"نتائج البحث عن: {q}"]
        for m in hits:
            lines.append(f"• [{m.role}] {(m.content or '')[:120]}")
        await update.effective_message.reply_text("\n".join(lines)[:3500])
    except Exception as exc:
        logger.exception("cmd_search")
        await update.effective_message.reply_text(f"تعذر البحث: {type(exc).__name__}")
