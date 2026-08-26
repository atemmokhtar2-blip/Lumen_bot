"""Emit handlers, keyboards, main.py registration for generated bots."""
from __future__ import annotations

from ..coding_emit_foundation import _msg
from ..registry import get_capability
from ..schema import BotSpec, Feature


def _handler_fname(feat: Feature) -> str:
    """Stable public handler name: handle_<capability> when known."""
    key = (getattr(feat, "feature", None) or getattr(feat, "id", "") or "").strip()
    if key and get_capability(key):
        return f"handle_{key}".replace("-", "_")
    fid = (getattr(feat, "id", None) or key or "cmd").replace("-", "_")
    return f"handle_{fid}"

def _emit_main(spec: BotSpec) -> str:
    commands: list[tuple[str, str]] = []
    handler_regs: list[str] = []
    skip_cmd_features = {"payment_precheckout", "payment_success"}
    for feat in spec.features:
        if feat.trigger.type != "command":
            continue
        if feat.feature in skip_cmd_features:
            continue
        cmd = feat.trigger.id
        if feat.feature == "start" or cmd == "start":
            handler_regs.append('    app.add_handler(CommandHandler("start", start_handler))')
            commands.append(("start", "start"))
        elif feat.feature == "help" or cmd == "help":
            handler_regs.append('    app.add_handler(CommandHandler("help", help_handler))')
            commands.append(("help", "help"))
        else:
            h = _handler_fname(feat)
            handler_regs.append(f'    app.add_handler(CommandHandler({cmd!r}, {h}))')
            commands.append((cmd, feat.feature))

    # ensure start/help registered
    reg_text = "\n".join(dict.fromkeys(handler_regs))
    if 'CommandHandler("start"' not in reg_text:
        reg_text = '    app.add_handler(CommandHandler("start", start_handler))\n' + reg_text
    if 'CommandHandler("help"' not in reg_text:
        reg_text += '\n    app.add_handler(CommandHandler("help", help_handler))'

    # Canonical aliases from command_map for every selected feature
    try:
        from lumen.engine.spec_core.command_map import commands_for_feature as _cmds_for
    except Exception:
        _cmds_for = lambda f: []  # type: ignore
    feat_to_handler = {
        f.feature: _handler_fname(f)
        for f in spec.features
        if f.feature not in ("start", "help", "payment_precheckout", "payment_success") and getattr(f.trigger, "type", "") == "command"
    }
    for f in spec.features:
        if f.feature in ("start", "help", "payment_precheckout", "payment_success"):
            continue
        hname = _handler_fname(f)
        feat_to_handler.setdefault(f.feature, hname)
    for feat, h in list(feat_to_handler.items()):
        if feat in {"payment_precheckout", "payment_success"}:
            continue
        for alias in _cmds_for(feat):
            if f"CommandHandler('{alias}'" in reg_text or f'CommandHandler("{alias}"' in reg_text:
                continue
            reg_text += f"\n    app.add_handler(CommandHandler({alias!r}, {h}))"

    need_tasks = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "tasks")  # type: ignore
        for f in spec.features
    )
    need_notes = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "notes")  # type: ignore
        for f in spec.features
    )
    need_reminders = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "reminders")  # type: ignore
        for f in spec.features
    )
    need_mod = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "moderation")  # type: ignore
        for f in spec.features
    )
    need_welcome = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "welcome")  # type: ignore
        for f in spec.features
    )
    need_ocr = any(
        (
            get_capability(f.feature)
            and (
                get_capability(f.feature).service == "ocr"  # type: ignore
                or get_capability(f.feature).method in {"ocr_hint", "ocr_image", "ocr"}  # type: ignore
                or str(f.feature).startswith("scaffold_ocr")
            )
        )
        for f in spec.features
    )
    need_pdf = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "pdf")
        for f in spec.features
    )

    need_voice = any(
        (
            get_capability(f.feature)
            and (
                get_capability(f.feature).method in {"voice_intake", "voice"}  # type: ignore
                or get_capability(f.feature).service == "voice"  # type: ignore
                or str(f.feature).startswith("scaffold_voice")
            )
        )
        for f in spec.features
    )
    need_sched = any(
        (
            get_capability(f.feature)
            and (
                get_capability(f.feature).service in {"scheduler", "reminders"}  # type: ignore
                or get_capability(f.feature).method in {"schedule_note", "job_list", "job_cancel"}  # type: ignore
                or str(f.feature).startswith("scaffold_schedule")
            )
        )
        for f in spec.features
    )
    need_tickets = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "tickets")  # type: ignore
        for f in spec.features
    )
    need_security = any(
        (get_capability(f.feature) and get_capability(f.feature).service == "security")  # type: ignore
        for f in spec.features
    )
    need_pay = any(
        (get_capability(f.feature) and get_capability(f.feature).service in {"shop", "payments", "cart", "subscriptions"})  # type: ignore
        for f in spec.features
    )
    # Import ONLY symbols that handlers.py actually defines.
    # payment_precheckout/success use pre_checkout_handler / successful_payment_handler.
    imports_handlers = "start_handler, help_handler, callback_router"
    extra_imports: list[str] = []
    _skip_import_features = {
        "start",
        "help",
        "payment_precheckout",
        "payment_success",
    }
    for feat in spec.features:
        if feat.feature in _skip_import_features:
            continue
        if feat.trigger.type not in ("command", "callback"):
            continue
        # Same naming rule as emission in _emit_handlers
        fname = _handler_fname(feat)
        extra_imports.append(fname)
    if extra_imports:
        imports_handlers += ", " + ", ".join(dict.fromkeys(extra_imports))
    need_market = any(
        (get_capability(f.feature) and get_capability(f.feature).service in {
            "shop", "payments", "subscriptions", "points", "contests",
            "cart", "growth", "wallet", "analytics", "admin",
        })  # type: ignore
        for f in spec.features
    )
    # Always imported — handlers.py always emits these (root: no silent free-text).
    imports_handlers += ", text_router, cancel_handler"
    if need_mod:
        imports_handlers += ", anti_abuse_filter"
    if need_ocr or need_pdf:
        if "photo_router" not in imports_handlers:
            imports_handlers += ", photo_router"
    if need_voice:
        if "voice_router" not in imports_handlers:
            imports_handlers += ", voice_router"
    if need_welcome:
        imports_handlers += ", chat_member_handler"
    if need_pay:
        imports_handlers += ", pre_checkout_handler, successful_payment_handler"

    # Telegram Bot API hard-limit: max 100 entries in set_my_commands.
    # CommandHandlers may still exceed 100; only the menu list is capped.
    _prio = {
        "start": 0, "help": 1, "shop": 2, "catalog": 3, "cart": 4, "orders": 5,
        "balance": 6, "plans": 7, "wallet": 8, "ticket": 9, "lang": 10,
    }
    uniq_cmds: list[tuple[str, str]] = []
    seen_c: set[str] = set()
    _bad_cmds = {"explicitcommand", "deeplinkstart", "smarthelp", "formstart"}
    for c, d in commands:
        c2 = "".join(ch for ch in (c or "").lower().replace("-", "_") if ch.isalnum() or ch == "_")[:32]
        if not c2 or c2 in seen_c or not c2[0].isalpha():
            continue
        if c2.replace("_", "") in _bad_cmds:
            continue
        seen_c.add(c2)
        desc = (d or c2).replace("_", " ").strip()[:48] or c2
        uniq_cmds.append((c2, desc))
    uniq_cmds.sort(key=lambda x: (_prio.get(x[0], 50), x[0]))
    menu_cmds = uniq_cmds[:100]
    bot_cmds = ",\n        ".join(
        f"BotCommand({c!r}, {d!r})" for c, d in menu_cmds
    ) or 'BotCommand("start", "start")'

    # Root: always wire free-text + cancel so user messages never vanish silently.
    # text_router and cancel_handler are always emitted by handlers.py.
    text_handler = (
        "\n    app.add_handler(CommandHandler('cancel', cancel_handler))"
        "\n    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))"
    )
    if need_mod:
        text_handler += "\n    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_abuse_filter), group=0)"
    if need_ocr or need_pdf:
        text_handler += "\n    app.add_handler(MessageHandler(filters.PHOTO, photo_router))"
    if need_voice:
        text_handler += (
            "\n    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_router))"
        )
    if need_welcome:
        text_handler += "\n    app.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.CHAT_MEMBER))"

    pay_handler = ""
    if need_pay:
        pay_handler = (
            "\n    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))"
            "\n    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))"
        )

    # Phase 12: JobQueue poller for due schedule_note rows (hardened)
    if need_sched:
        sched_job_block = '''
async def _fire_due_reminders(context) -> None:
    """Poll open reminders and deliver to stored chat_id. Cap batch to avoid flood."""
    try:
        import os as _os
        if (_os.getenv("SCHEDULE_ENABLED") or "1").strip().lower() in {"0", "false", "no"}:
            return
        from app.services import reminders as reminders_svc
        batch = int((_os.getenv("SCHEDULE_BATCH_LIMIT") or "20").strip() or "20")
        due = reminders_svc.list_due_reminders(limit=max(1, min(batch, 50)))
        sent = 0
        for item in due:
            chat_id = int(item.get("chat_id") or item.get("user_id") or 0)
            body = str(item.get("body") or "")
            iid = item.get("id")
            ok = False
            if chat_id and body:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"⏰ تذكير #{iid}\\n{body[:500]}",
                    )
                    ok = True
                    sent += 1
                except Exception as send_exc:
                    logger.warning(
                        "reminder send failed id=%s chat_id=%s: %s",
                        iid, chat_id, send_exc,
                    )
            # mark fired only on successful delivery (or empty payload — avoid loops)
            if iid is not None and (ok or not (chat_id and body)):
                try:
                    reminders_svc.mark_reminder_fired(int(iid))
                except Exception as mark_exc:
                    logger.warning("mark_reminder_fired id=%s: %s", iid, mark_exc)
        if sent:
            logger.info("due_reminders delivered=%s batch=%s", sent, len(due))
    except Exception as exc:
        logger.warning("fire_due_reminders: %s", exc)
'''
        sched_post_init = '''
    # Phase 12 JobQueue: poll due reminders every 60s
    try:
        if app.job_queue is not None:
            app.job_queue.run_repeating(_fire_due_reminders, interval=60, first=15, name="due_reminders")
            logger.info("JobQueue due_reminders scheduled")
        else:
            logger.warning("JobQueue unavailable — install python-telegram-bot[job-queue]")
    except Exception as exc:
        logger.warning("JobQueue setup failed: %s", exc)
'''
    else:
        sched_job_block = ""
        sched_post_init = ""

    return f'''"""Application entry — python-telegram-bot v21."""
from __future__ import annotations

import logging
import sys

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from app.config import get_settings
from app.handlers import {imports_handlers}
from app.sentry_setup import init_sentry, ptb_error_handler

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger({spec.bot.name!r})


{sched_job_block}
async def _post_init(app: Application) -> None:
    # Telegram allows at most 100 bot commands in the menu.
    try:
        await app.bot.set_my_commands([
            {bot_cmds}
        ])
    except Exception as exc:
        logger.warning("set_my_commands skipped: %s", exc)
{sched_post_init}

def build_application() -> Application:
    init_sentry(bot_name={spec.bot.name!r})
    settings = get_settings()
    token = settings.require_token()
    app = (
        Application.builder()
        .token(token)
        .post_init(_post_init)
        .concurrent_updates(True)
        .build()
    )
{reg_text}
    app.add_handler(CallbackQueryHandler(callback_router)){text_handler}{pay_handler}
    app.add_error_handler(ptb_error_handler)
    return app


def main() -> None:
    logger.info("starting bot name=%s", {spec.bot.name!r})
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
'''


