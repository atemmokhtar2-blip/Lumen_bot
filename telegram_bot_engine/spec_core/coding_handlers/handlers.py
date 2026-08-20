"""Emit handlers, keyboards, main.py registration for generated bots."""
from __future__ import annotations

from ..coding_emit_foundation import _msg
from ..registry import get_capability
from ..schema import BotSpec, Feature

from .market_lines import _market_handler_lines

def _emit_handlers(spec: BotSpec) -> str:
    lang = (spec.bot.language or "ar").lower()
    n_cmds = len([f for f in spec.features if f.trigger.type == "command"])
    bot_name = (getattr(spec.bot, "name", None) or "Bot").strip() or "Bot"
    _HELP_AR = {
        "start": "البداية",
        "help": "المساعدة",
        "lang": "تغيير اللغة",
        "task_add": "إضافة مهمة",
        "task_list": "عرض مهامي",
        "task_delete": "حذف مهمة بالرقم",
        "task_done": "إنهاء مهمة بالرقم",
        "task_clear": "مسح المهام المنتهية",
        "remind_set": "ضبط تذكير (مثال: اجتماع بعد 30 دقيقة)",
        "remind_list": "عرض التذكيرات",
        "note_add": "إضافة ملاحظة",
        "note_list": "عرض الملاحظات",
        "clinic_book": "حجز موعد طبي",
        "clinic_my": "مواعيدي الطبية",
        "clinic_cancel": "إلغاء موعد طبي",
        "clinic_slots": "المواعيد المتاحة",
        "book_slot": "حجز موعد",
        "book_list": "حجوزاتي",
        "book_cancel": "إلغاء حجز",
        "shop_catalog": "عرض المنتجات",
        "cart_view": "عرض السلة",
        "ticket_open": "فتح تذكرة دعم",
        "ticket_list": "قائمة التذاكر",
        "ticket_status": "حالة تذكرة",
        "sec_dns_check": "فحص DNS لنطاق",
        "sec_tls_check": "فحص شهادة SSL",
        "sec_domain_overview": "نظرة عامة على النطاق",
        "user_ban": "حظر عضو (بالرد على رسالته)",
        "user_unban": "فك حظر عضو",
        "user_mute": "كتم عضو (بالرد)",
        "user_unmute": "فك كتم عضو",
        "user_kick": "طرد عضو (بالرد)",
        "user_warn": "تحذير عضو (بالرد)",
        "user_info": "معلومات العضو (بالرد)",
        "delete_message": "حذف رسالة (بالرد)",
        "purge": "تنظيف رسائل",
        "welcome_set": "تعيين رسالة الترحيب",
        "welcome_toggle": "تشغيل/إيقاف الترحيب",
        "rules": "عرض القوانين",
    }
    feat_keys = {getattr(f, "feature", "") for f in (spec.features or [])}
    if lang.startswith("ar"):
        tips = []
        if feat_keys & {"task_add", "task_list"}:
            tips.append("• المهام: /add عنوان المهمة — ثم /list لعرضها")
        if feat_keys & {"remind_set", "remind_list"}:
            tips.append("• التذكير: /remindset اجتماع بعد 30 دقيقة")
        if feat_keys & {"clinic_book", "book_slot"}:
            tips.append("• المواعيد: /clinicbook كشف غداً 10 ص")
        if feat_keys & {"shop_catalog", "cart_view"}:
            tips.append("• المتجر: من الأزرار أو /shopcatalog")
        if feat_keys & {"ticket_open"}:
            tips.append("• الدعم: /ticketopen موضوع المشكلة")
        if feat_keys & {"sec_dns_check"}:
            tips.append("• الأمان: /secdnscheck example.com")
        tip_block = ("\n".join(tips) + "\n") if tips else ""
        welcome = (
            f"مرحباً بك في {bot_name} 👋\n"
            f"بوت جاهز للاستخدام — {n_cmds} أمر متاح.\n"
            f"{tip_block}"
            "اضغط الأزرار بالأسفل أو اكتب /help لعرض كل الأوامر."
        )
    else:
        welcome = (
            f"Welcome to {bot_name} 👋\n"
            f"{n_cmds} commands ready.\n"
            "Use the menu buttons or /help."
        )

    help_lines = []
    help_lines.append(
        f"📋 قائمة الأوامر ({n_cmds}):" if lang.startswith("ar") else f"Commands ({n_cmds}):"
    )
    for feat in spec.features:
        if feat.trigger.type == "command":
            if lang.startswith("ar"):
                desc = (
                    feat.messages.prompt
                    or _HELP_AR.get(feat.feature)
                    or feat.feature.replace("_", " ")
                )
            else:
                desc = feat.messages.prompt or feat.feature.replace("_", " ")
            help_lines.append(f"/{feat.trigger.id} — {desc}")
    if lang.startswith("ar"):
        help_lines.append("")
        help_lines.append("💡 نصيحة: الأزرار تحت الرسالة تنفّذ نفس الأوامر.")
    help_text = "\n".join(help_lines) if help_lines else "/start"
    help_text = "\n".join(help_lines) if help_lines else "/start"

    # collect needs
    def _svc(f):
        c = get_capability(f.feature)
        return c.service if c else ""

    need_mod = any(_svc(f) == "moderation" for f in spec.features)
    need_tasks = any(_svc(f) == "tasks" for f in spec.features)
    need_notes = any(_svc(f) == "notes" for f in spec.features)
    need_reminders = any(_svc(f) == "reminders" for f in spec.features)
    need_content = any(_svc(f) == "content" for f in spec.features)
    need_welcome = any(_svc(f) == "welcome" for f in spec.features)
    need_tickets = any(_svc(f) == "tickets" for f in spec.features)
    need_security = any(_svc(f) == "security" for f in spec.features)
    need_pubg = any(_svc(f) == "pubg" for f in spec.features)
    need_ocr = any(
        _svc(f) == "ocr"
        or (getattr(get_capability(f.feature), "method", None) in {"ocr_hint", "ocr_image", "ocr"})
        or str(f.feature).startswith("scaffold_ocr")
        for f in spec.features
    )
    need_voice = any(
        (getattr(get_capability(f.feature), "method", None) in {"voice_intake", "voice"})
        or str(f.feature).startswith("scaffold_voice")
        or _svc(f) == "voice"
        for f in spec.features
    )
    need_market = any(
        _svc(f) in {
            'shop', 'payments', 'subscriptions', 'points', 'contests',
            'cart', 'growth', 'wallet', 'analytics', 'admin',
        }
        for f in spec.features
    )
    _extra_set = {"shop", "booking", "crm", "community", "edu", "hr", "utils", "gate"}
    need_extras = any(_svc(f) in _extra_set for f in spec.features)

    imports = [
        "from __future__ import annotations",
        "",
        "from telegram import Update",
        "from telegram.ext import ContextTypes",
        "from app.keyboards import main_keyboard",
    ]
    if need_mod:
        imports.append("from app.services import moderation as moderation_svc")
    if need_tasks:
        imports.append("from app.services import tasks as tasks_svc")
    if need_notes:
        imports.append("from app.services import notes as notes_svc")
    if need_reminders:
        imports.append("from app.services import reminders as reminders_svc")

    if need_content:
        imports.append("from app.services import content as content_svc")
    if need_welcome:
        imports.append("from app.services import welcome as welcome_svc")
    if need_tickets:
        imports.append("from app.services import tickets as tickets_svc")
    if need_security:
        imports.append("from app.services import security as security_svc")
    if need_pubg:
        imports.append("from app.services import pubg as pubg_svc")
    if need_extras:
        imports.append("from app.services import extras as extras_svc")

    lines: list[str] = imports + ["", ""]

    # i18n helper only when commerce strings are used
    if need_market:
        if lang.startswith("en"):
            _i18n = {
                "usage_cart_add": "Usage: /cartadd <product_id> [qty]",
                "insufficient_balance": "Insufficient balance",
                "order_cancelled": "Order cancelled",
                "invalid_number": "Invalid number",
                "product_added": "Product added",
                "coming_soon": "This feature is coming soon.",
            }
        else:
            _i18n = {
                "usage_cart_add": "الاستخدام: /cartadd <معرف_المنتج> [الكمية]",
                "insufficient_balance": "الرصيد غير كافٍ",
                "order_cancelled": "تم إلغاء الطلب",
                "invalid_number": "رقم غير صالح",
                "product_added": "تمت إضافة المنتج",
                "coming_soon": "هذه الميزة قريباً.",
            }
        lines += [f"_I18N = {_i18n!r}", "def t(key: str) -> str:", "    return _I18N.get(key, key)", "", ""]

    # start / help always useful
    lines += [
        "async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
        "    message = update.effective_message",
        "    user = update.effective_user",
        "    if message is None:",
        "        return",
        f"    text = {welcome!r}",
        "    kb = main_keyboard()",
        "    await message.reply_text(text, reply_markup=kb)",
        "",
        "",
        "async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
        "    message = update.effective_message",
        "    if message is None:",
        "        return",
        f"    await message.reply_text({help_text!r})",
        "",
        "",
    ]

    # feature handlers — ALWAYS emit a function for every command feature so
    # main.py CommandHandler bindings never point at missing symbols.
    emitted_fnames: set[str] = set()
    for feat in spec.features:
        if feat.trigger.type != "command":
            continue
        if feat.feature in ("start", "help") or feat.trigger.id in ("start", "help"):
            continue
        if feat.feature in {"payment_precheckout", "payment_success"}:
            continue
        # Never emit ghost capabilities that produce /explicitcommand style noise
        if feat.feature in {"explicit_command", "deep_link_start", "smart_help", "form_start"}:
            if feat.feature == "explicit_command" and str(feat.trigger.id or "") in {"about", "info"}:
                pass  # allow about mapped as explicit_command with about trigger
            else:
                continue
        trig = str(feat.trigger.id or "").lower().replace("-", "").replace("_", "")
        if trig in {"explicitcommand", "deeplinkstart", "smarthelp", "formstart"}:
            continue
        fname = f"handle_{feat.id}".replace("-", "_")
        if fname in emitted_fnames:
            continue
        emitted_fnames.add(fname)
        cap = get_capability(feat.feature)
        ok = _msg(feat, "success", "تم بنجاح" if lang.startswith("ar") else "Done")
        fail = _msg(feat, "failure", "فشل التنفيذ" if lang.startswith("ar") else "Failed")

        if cap is not None and cap.method == "start":
            continue  # already have start_handler
        if cap is not None and cap.method == "help":
            continue

        lines.append(f"async def {fname}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
        lines.append("    message = update.effective_message")
        lines.append("    user = update.effective_user")
        lines.append("    chat = update.effective_chat")
        lines.append("    if message is None or user is None:")
        lines.append("        return")

        if cap is None:
            # Unknown capability — still a real handler (not a stub empty body)
            label = (feat.feature or feat.trigger.id or "feature").replace("_", " ")
            lines.append(f"    await message.reply_text({(label + ' — OK')!r})")
            lines.append("")
            continue

        if cap.service == "moderation":
            if cap.method in {"pin_message", "delete_message", "purge"}:
                lines.append("    if chat is None or message.reply_to_message is None:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        mid = message.reply_to_message.message_id")
                lines.append(f"        await moderation_svc.{cap.method}(context, chat.id, mid)")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    except Exception:")
                lines.append(f"        await message.reply_text({fail!r})")
            elif cap.method in {
                "list_log", "list_forbidden", "set_protection", "set_max_warns",
                "slowmode_info", "add_forbidden", "remove_forbidden",
            }:
                lines.append("    if chat is None:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                if cap.method == "list_log":
                    lines.append("        await message.reply_text(moderation_svc.list_log(chat.id))")
                elif cap.method == "list_forbidden":
                    lines.append("        words = moderation_svc.list_forbidden(chat.id)")
                    lines.append("        await message.reply_text('\\n'.join(words) if words else 'لا كلمات ممنوعة')")
                elif cap.method == "set_protection":
                    lines.append("        await message.reply_text(moderation_svc.set_protection(chat.id))")
                elif cap.method == "set_max_warns":
                    lines.append("        n = int(context.args[0]) if context.args else 3")
                    lines.append("        await message.reply_text(moderation_svc.set_max_warns(chat.id, n))")
                elif cap.method == "add_forbidden":
                    lines.append("        w = ' '.join(context.args) if context.args else ''")
                    lines.append("        await message.reply_text(moderation_svc.add_forbidden(chat.id, w))")
                elif cap.method == "remove_forbidden":
                    lines.append("        w = ' '.join(context.args) if context.args else ''")
                    lines.append("        await message.reply_text(moderation_svc.remove_forbidden(chat.id, w))")
                else:
                    lines.append("        await message.reply_text(moderation_svc.slowmode_info())")
                lines.append("    except Exception:")
                lines.append(f"        await message.reply_text({fail!r})")
            else:
                lines.append("    target_id = None")
                lines.append("    if message.reply_to_message and message.reply_to_message.from_user:")
                lines.append("        target_id = message.reply_to_message.from_user.id")
                lines.append("    elif context.args:")
                lines.append("        try:")
                lines.append("            target_id = int(context.args[0])")
                lines.append("        except ValueError:")
                lines.append("            target_id = None")
                lines.append("    if target_id is None or chat is None:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                method_map = {
                    "ban_user": "ban_user",
                    "unban_user": "unban_user",
                    "mute_user": "mute_user",
                    "unmute_user": "unmute_user",
                    "kick_user": "kick_user",
                    "promote_user": "promote_user",
                    "demote_user": "demote_user",
                    "warn_user": "warn_user",
                }
                if cap.method == "user_info":
                    lines.append("        await message.reply_text(moderation_svc.user_info(target_id, chat.id))")
                    lines.append("        return")
                if cap.method == "unwarn_user":
                    lines.append("        await message.reply_text(moderation_svc.unwarn_user(chat.id, target_id))")
                    lines.append("        return")
                if cap.method == "clear_warnings":
                    lines.append("        await message.reply_text(moderation_svc.clear_warnings(chat.id, target_id))")
                    lines.append("        return")
                if cap.method == "get_warns":
                    lines.append("        n = moderation_svc.get_warns(chat.id, target_id)")
                    lines.append("        await message.reply_text(f'تحذيرات {target_id}: {n}')")
                    lines.append("        return")
                if cap.method == "set_owner":
                    lines.append("        await message.reply_text(moderation_svc.set_owner(chat.id, target_id))")
                    lines.append("        return")
                if cap.method == "set_role":
                    lines.append("        role = context.args[1] if context.args and len(context.args) > 1 else 'moderator'")
                    lines.append("        await message.reply_text(moderation_svc.set_role(chat.id, target_id, role))")
                    lines.append("        return")
                m = method_map.get(cap.method, "warn_user")
                if m == "warn_user":
                    lines.append("        msg = await moderation_svc.warn_user(context, chat.id, target_id, admin_id=user.id)")
                    lines.append("        await message.reply_text(msg)")
                else:
                    lines.append(f"        await moderation_svc.{m}(context, chat.id, target_id)")
                    lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    except Exception:")
                lines.append(f"        await message.reply_text({fail!r})")

        elif cap.service == "pubg":
            lines.append("    if chat is None:")
            lines.append(f"        await message.reply_text({fail!r})")
            lines.append("        return")
            lines.append("    args = context.args or []")
            lines.append("    try:")
            lines.append(f"        _m = {cap.method!r}")
            lines.append("        if _m == 'register_player':")
            lines.append("            ign = ' '.join(args) if args else ''")
            lines.append("            await message.reply_text(pubg_svc.register_player(chat.id, user.id, ign))")
            lines.append("        elif _m == 'list_players':")
            lines.append("            await message.reply_text(pubg_svc.list_players(chat.id))")
            lines.append("        elif _m == 'set_team':")
            lines.append("            team = ' '.join(args) if args else ''")
            lines.append("            await message.reply_text(pubg_svc.set_team(chat.id, user.id, team))")
            lines.append("        elif _m == 'list_teams':")
            lines.append("            await message.reply_text(pubg_svc.list_teams(chat.id))")
            lines.append("        elif _m == 'record_match':")
            lines.append("            note = ' '.join(args) if args else ''")
            lines.append("            await message.reply_text(pubg_svc.record_match(chat.id, user.id, note=note))")
            lines.append("        elif _m == 'top_players':")
            lines.append("            await message.reply_text(pubg_svc.top_players(chat.id))")
            lines.append("        elif _m == 'player_stats':")
            lines.append("            uid = int(args[0]) if args and str(args[0]).isdigit() else user.id")
            lines.append("            await message.reply_text(pubg_svc.player_stats(chat.id, uid))")
            lines.append("        elif _m == 'create_tournament':")
            lines.append("            title = ' '.join(args) if args else 'Tournament'")
            lines.append("            await message.reply_text(pubg_svc.create_tournament(chat.id, user.id, title))")
            lines.append("        else:")
            lines.append(f"            await message.reply_text({ok!r})")
            lines.append("    except Exception:")
            lines.append(f"        await message.reply_text({fail!r})")

        elif cap.service == "tasks":
            if cap.method == "add_task":
                prompt = _msg(feat, "prompt", "أرسل عنوان المهمة" if lang.startswith("ar") else "Send task title")
                lines.append("    if context.args:")
                lines.append("        title = ' '.join(context.args)")
                lines.append("        tasks_svc.add_task(user.id, title)")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("        return")
                lines.append("    context.user_data['awaiting'] = 'task_title'")
                lines.append(f"    await message.reply_text({prompt!r})")
            elif cap.method == "list_tasks":
                empty = "لا توجد مهام" if lang.startswith("ar") else "No tasks"
                lines.append("    items = tasks_svc.list_tasks(user.id)")
                lines.append("    if not items:")
                lines.append(f"        await message.reply_text({empty!r})")
                lines.append("        return")
                lines.append("    text = \"\\n\".join(f\"#{i['id']} {i['title']} [{i['priority']}]\" for i in items)")
                lines.append("    await message.reply_text(text)")
            elif cap.method == "done_task":
                usage = "الاستخدام: /done <رقم_المهمة> — مثال: /done 3" if lang.startswith("ar") else "Usage: /done <task_id>"
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({usage!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({usage!r})")
                lines.append("        return")
                lines.append("    if tasks_svc.done_task(user.id, tid):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            elif cap.method == "delete_task":
                usage = "الاستخدام: /delete <رقم_المهمة> — مثال: /delete 3" if lang.startswith("ar") else "Usage: /delete <task_id>"
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({usage!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({usage!r})")
                lines.append("        return")
                lines.append("    if tasks_svc.delete_task(user.id, tid):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            elif cap.method == "clear_tasks":
                lines.append("    n = tasks_svc.clear_tasks(user.id)")
                lines.append(f"    await message.reply_text({ok!r} + f' ({{n}})')")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        elif cap.service == "notes":
            if cap.method == "add_note":
                prompt = _msg(feat, "prompt", "أرسل نص الملاحظة" if lang.startswith("ar") else "Send note text")
                lines.append("    if context.args:")
                lines.append("        notes_svc.add_note(user.id, ' '.join(context.args))")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("        return")
                lines.append("    context.user_data['awaiting'] = 'note_body'")
                lines.append(f"    await message.reply_text({prompt!r})")
            elif cap.method == "list_notes":
                empty = "لا توجد ملاحظات" if lang.startswith("ar") else "No notes"
                lines.append("    items = notes_svc.list_notes(user.id)")
                lines.append("    if not items:")
                lines.append(f"        await message.reply_text({empty!r})")
                lines.append("        return")
                lines.append("    text = \"\\n\".join(f\"#{i['id']} {i['body']}\" for i in items)")
                lines.append("    await message.reply_text(text)")
            elif cap.method == "delete_note":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        nid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    if notes_svc.delete_note(user.id, nid):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        elif cap.service == "content":
            if cap.method == "rules":
                lines.append("    await message.reply_text(content_svc.rules())")
            elif cap.method == "faq":
                # Prefer durable FAQ scaffold (search + seed) when available
                lines.append("    from app.services import generic as generic_svc")
                lines.append(
                    "    if hasattr(generic_svc, 'faq'):"
                )
                lines.append(
                    "        result = generic_svc.faq(user.id, ' '.join(context.args) if context.args else '')"
                )
                lines.append("        await message.reply_text(result)")
                lines.append("    else:")
                lines.append(
                    "        await message.reply_text(content_svc.faq() if hasattr(content_svc, 'faq') else content_svc.rules())"
                )
            elif cap.method == "announce":
                lines.append("    body = ' '.join(context.args) if context.args else ''")
                lines.append("    if not body:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append(f"    await message.reply_text({ok!r} + \"\\n\" + body)")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        elif cap.service == "core":
            if cap.method == "about":
                about = spec.bot.description or spec.bot.name
                lines.append(f"    await message.reply_text({about!r})")
            elif cap.method == "ping":
                lines.append("    await message.reply_text('pong')")
            elif cap.method == "my_id":
                lines.append("    chat_id = chat.id if chat else 0")
                lines.append("    await message.reply_text(f'user_id={user.id}\\nchat_id={chat_id}')")
            elif cap.method == "settings":
                lines.append("    await message.reply_text('الإعدادات: اللغة العربية افتراضيًا')")
            elif cap.method == "language":
                lines.append("    await message.reply_text('اللغة الحالية: العربية')")
            elif cap.method == "cancel":
                lines.append("    context.user_data.clear()")
                lines.append("    await message.reply_text('تم الإلغاء')")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        elif cap.service == "welcome":
            lines.append("    if chat is None:")
            lines.append(f"        await message.reply_text({fail!r})")
            lines.append("        return")
            if cap.method == "set_message":
                lines.append("    if context.args:")
                lines.append("        welcome_svc.set_message(chat.id, ' '.join(context.args))")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("        return")
                lines.append("    context.user_data['awaiting'] = 'welcome_message'")
                lines.append("    await message.reply_text('أرسل نص الترحيب. استخدم {name} لاسم العضو')")
            elif cap.method == "toggle":
                lines.append("    enabled = welcome_svc.toggle(chat.id)")
                lines.append("    await message.reply_text('الترحيب مفعّل' if enabled else 'الترحيب متوقف')")
            elif cap.method == "show":
                lines.append("    cfg = welcome_svc.get_settings(chat.id)")
                lines.append("    state = 'مفعّل' if cfg['enabled'] else 'متوقف'")
                lines.append('    await message.reply_text(f"الحالة: {state}\\nالرسالة:\\n{cfg[\'message\']}")')
            elif cap.method == "test":
                lines.append("    name = user.full_name if user else 'عضو'")
                lines.append("    text = welcome_svc.format_welcome(chat.id, name) or 'الترحيب متوقف'")
                lines.append("    await message.reply_text(text)")
            else:
                lines.append(f"    await message.reply_text({ok!r})")

        elif cap.service == "tickets":
            if cap.method == "open_ticket":
                lines.append("    if context.args:")
                lines.append("        subject = ' '.join(context.args)")
                lines.append("        tid = tickets_svc.open_ticket(user.id, subject, chat.id if chat else 0)")
                lines.append(f"        await message.reply_text({ok!r} + f' #{{tid}}')")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        from app.flow_engine import start_flow")
                lines.append("        await start_flow(update, context, 'open_ticket')")
                lines.append("    except Exception:")
                lines.append("        context.user_data['awaiting'] = 'ticket_subject'")
                lines.append("        await message.reply_text('اكتب موضوع تذكرة الدعم')")
            elif cap.method == "close_ticket":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    ok_close = tickets_svc.close_ticket(tid, user_id=user.id, staff=False)")
                lines.append("    if not ok_close:")
                lines.append("        ok_close = tickets_svc.close_ticket(tid, staff=True)")
                lines.append(f"    await message.reply_text({ok!r} if ok_close else {fail!r})")
            elif cap.method == "my_tickets":
                lines.append("    items = tickets_svc.my_tickets(user.id)")
                lines.append("    if not items:")
                lines.append("        await message.reply_text('لا توجد تذاكر مفتوحة')")
                lines.append("        return")
                lines.append('    text = "\\n".join(f"#{i[\'id\']} [{i[\'status\']}] {i[\'subject\']}" for i in items)')
                lines.append("    await message.reply_text(text)")
            elif cap.method == "list_tickets":
                lines.append("    items = tickets_svc.list_tickets(only_open=True)")
                lines.append("    if not items:")
                lines.append("        await message.reply_text('لا توجد تذاكر مفتوحة')")
                lines.append("        return")
                lines.append('    text = "\\n".join(f"#{i[\'id\']} u={i[\'user_id\']} [{i[\'status\']}] {i[\'subject\']}" for i in items)')
                lines.append("    await message.reply_text(text)")
            elif cap.method == "reply_ticket":
                lines.append("    if len(context.args or []) < 2:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    body = ' '.join(context.args[1:])")
                lines.append("    if tickets_svc.reply_ticket(tid, user.id, body, staff=True):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            elif cap.method == "ticket_status":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    data = tickets_svc.ticket_status(tid)")
                lines.append("    if not data:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    msgs = data.get('messages') or []")
                lines.append("    parts = []")
                lines.append("    for m in msgs[-5:]:")
                lines.append("        role = 'staff' if m['is_staff'] else 'user'")
                lines.append('        parts.append(f"- {role}: {m[\'body\']}")')
                lines.append('    tail = "\\n".join(parts)')
                lines.append('    await message.reply_text(f"#{data[\'id\']} [{data[\'status\']}] {data[\'subject\']}\\n{tail}")')
            else:
                lines.append(f"    await message.reply_text({ok!r})")


        elif cap.service == "security":
            if cap.method == "checklist":
                lines.append("    await message.reply_text(security_svc.checklist())")
            elif cap.method == "tips":
                lines.append("    await message.reply_text(security_svc.tips())")
            elif cap.method == "password_tips":
                lines.append("    await message.reply_text(security_svc.password_tips())")
            elif cap.method in {"report_phish", "report_incident"}:
                kind = "phish" if cap.method == "report_phish" else "incident"
                lines.append("    if context.args:")
                lines.append(f"        rid = security_svc.report(user.id, {kind!r}, ' '.join(context.args))")
                lines.append(f"        await message.reply_text({ok!r} + f' #{{rid}}')")
                lines.append("        return")
                lines.append(f"    context.user_data['awaiting'] = 'sec_{kind}'")
                lines.append("    await message.reply_text('صف البلاغ بإيجاز (رابط/وصف)')")
            elif cap.method == "list_reports":
                lines.append("    items = security_svc.list_reports(only_open=True)")
                lines.append("    if not items:")
                lines.append("        await message.reply_text('لا بلاغات مفتوحة')")
                lines.append("        return")
                lines.append('    text = "\\n".join(f"#{i[\'id\']} [{i[\'kind\']}] {i[\'body\'][:60]}" for i in items)')
                lines.append("    await message.reply_text(text)")
            elif cap.method == "close_report":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        rid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    if security_svc.close_report(rid):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            elif cap.method in {
                "dns_check", "mx_check", "tls_check", "http_check",
                "headers_check", "domain_overview",
            }:
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r} or 'أدخل النطاق: مثال example.com')")
                lines.append("        return")
                lines.append("    host = context.args[0]")
                lines.append(f"    result = security_svc.{cap.method}(host)")
                lines.append("    await message.reply_text(result)")
            else:
                lines.append(f"    await message.reply_text({ok!r})")


        elif cap.service in {
            "shop", "payments", "subscriptions", "points", "contests",
            "cart", "growth", "wallet", "i18n", "creator",
            "compliance", "analytics", "admin", "notify",
        }:
            lines.extend(_market_handler_lines(cap, ok, fail))
        elif cap.service == "booking":
            lines.append("    from app.services import booking as booking_svc")
            lines.append(
                f"    result = booking_svc.act('booking', {cap.method!r}, user.id, "
                "' '.join(context.args) if context.args else '')"
            )
            lines.append("    await message.reply_text(result)")
        elif cap.service == "clinic":
            lines.append("    from app.services import clinic as clinic_svc")
            if cap.method in {"book", "book_slot", "add"}:
                lines.append("    arg = ' '.join(context.args) if context.args else ''")
                lines.append("    if not arg:")
                lines.append("        context.user_data['awaiting'] = 'clinic_book'")
                lines.append("        await message.reply_text('أرسل وصف الموعد — مثال: كشف غداً الساعة 10 صباحاً')")
                lines.append("        return")
                lines.append("    result = clinic_svc.book(user.id, arg)")
            elif cap.method in {"cancel"}:
                lines.append("    arg = ' '.join(context.args) if context.args else ''")
                lines.append("    if not arg:")
                lines.append("        await message.reply_text('الاستخدام: /cliniccancel <رقم_الموعد> — شوف الرقم من /clinicmy')")
                lines.append("        return")
                lines.append("    result = clinic_svc.cancel(user.id, arg)")
            elif cap.method in {"my_appointments", "my", "list"}:
                lines.append("    result = clinic_svc.my_appointments(user.id)")
            elif cap.method in {"slots", "list_slots"}:
                lines.append("    result = clinic_svc.slots(user.id)")
            else:
                lines.append(
                    f"    result = clinic_svc.act('clinic', {cap.method!r}, user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
            lines.append("    await message.reply_text(result)")
        elif cap.service == "reminders":
            lines.append("    from app.services import reminders as reminders_svc")
            if cap.method in {"set_reminder", "set", "add"}:
                lines.append("    arg = ' '.join(context.args) if context.args else ''")
                lines.append("    if not arg:")
                lines.append("        context.user_data['awaiting'] = 'reminder_body'")
                lines.append(
                    "        await message.reply_text("
                    "'أرسل نص التذكير والوقت — مثال: اجتماع بعد 30 دقيقة')"
                )
                lines.append("        return")
                lines.append("    chat_id = chat.id if chat is not None else user.id")
                lines.append("    rid = reminders_svc.set_reminder(user.id, arg, chat_id=chat_id)")
                lines.append("    await message.reply_text(f'تم ضبط التذكير #{rid}')")
            elif cap.method in {"list_reminders", "list"}:
                lines.append("    items = reminders_svc.list_reminders(user.id)")
                lines.append("    if not items:")
                lines.append("        await message.reply_text('لا توجد تذكيرات مفتوحة')")
                lines.append("        return")
                lines.append(
                    "    text = '\\n'.join("
                    "f\"#{i['id']} خلال {i.get('remain_min', 0)} د — {i['body']}\" for i in items)"
                )
                lines.append("    await message.reply_text(text)")
            elif cap.method in {"clear_reminders", "clear"}:
                lines.append("    n = reminders_svc.clear_reminders(user.id)")
                lines.append("    await message.reply_text(f'تم إغلاق {n} تذكير')")
            else:
                lines.append(
                    f"    result = reminders_svc.act('reminders', {cap.method!r}, user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
                lines.append("    await message.reply_text(result)")
        elif cap.service in {"translate", "ocr", "scheduler"} or (
            cap.service in {"utils", "content", "generic"}
            and cap.method
            in {
                "translate",
                "translate_toggle",
                "ocr_image",
                "ocr_hint",
                "ocr",
                "job_list",
                "list_jobs",
                "job_cancel",
                "cancel_job",
                "schedule_note",
                "voice_intake",
                "payment_info",
                "faq",
            }
        ):
            lines.append("    from app.services import generic as generic_svc")
            if cap.method in {"voice_intake"}:
                lines.append(
                    "    result = generic_svc.voice_intake(user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
            elif cap.method in {"payment_info", "pay_info"}:
                lines.append(
                    "    result = generic_svc.payment_info(user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
            elif cap.method in {"faq"}:
                lines.append(
                    "    result = generic_svc.faq(user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
            elif cap.method in {"translate", "translate_toggle"} or cap.service == "translate":
                lines.append(
                    "    result = generic_svc.translate_text(user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
            elif cap.method in {"ocr_image", "ocr_hint", "ocr"} or cap.service == "ocr":
                lines.append("    args = ' '.join(context.args) if context.args else ''")
                lines.append("    if args:")
                lines.append("        result = generic_svc.ocr_hint(user.id, args)")
                lines.append("        await message.reply_text(result)")
                lines.append("        return")
                lines.append("    context.user_data['awaiting'] = 'ocr_photo'")
                lines.append(
                    "    result = generic_svc.ocr_hint(user.id, '')"
                )
            elif cap.method in {"job_list", "list_jobs"}:
                lines.append("    result = generic_svc.job_list(user.id, '')")
            elif cap.method in {"job_cancel", "cancel_job"}:
                lines.append(
                    "    result = generic_svc.job_cancel(user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
            else:
                lines.append(
                    "    result = generic_svc.schedule_note(user.id, "
                    "' '.join(context.args) if context.args else '', "
                    "chat_id=(chat.id if chat else user.id))"
                )
            lines.append("    await message.reply_text(result)")
        else:
            # Prefer lightweight handlers for simple explicit commands (e.g. /about).
            # Only pull the fat generic runtime for non-trivial service methods.
            if cap.method == "explicit_command":
                tid = (feat.trigger.id or "command").replace("'", "")
                lines.append(f"    _cmd = {tid!r}")
                lines.append("    if _cmd in {'about', 'info'}:")
                lines.append("        await message.reply_text('بوت تيليجرام جاهز. استخدم /help لعرض الأوامر.')")
                lines.append("    else:")
                lines.append("        await message.reply_text(f'أمر /{_cmd} — جاهز.')")
            else:
                lines.append("    from app.services import generic as generic_svc")
                lines.append(
                    f"    result = generic_svc.act({cap.service!r}, {cap.method!r}, user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
                lines.append("    await message.reply_text(result)")
        lines.append("")
        lines.append("")

    # text router for multi-step captures
    if need_tasks or need_notes or need_reminders or need_welcome or need_tickets or need_security or need_market or need_ocr or need_voice or need_mod:
        lines += [
            "async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    chat = update.effective_chat",
            "    if message is None or user is None:",
            "        return",
            *(
                [
                    "    # Dynamic multi-step flow engine (wizard)",
                    "    try:",
                    "        from app.flow_engine import handle_text as _flow_text, active_flow",
                    "        if active_flow(context) or context.user_data.get('flow'):",
                    "            if message.text and await _flow_text(update, context):",
                    "                return",
                    "    except Exception as _flow_exc:",
                    "        import logging as _logging",
                    "        _logging.getLogger(__name__).debug('flow text: %s', _flow_exc)",
                ]
                if (need_market or need_tickets)
                else []
            ),
            "    if not message.text:",
            "        return",
            "    awaiting = context.user_data.get('awaiting')",
            *(
                [
                    "    if isinstance(awaiting, str) and awaiting.startswith('mkt_'):",
                    "        text = (message.text or '').strip()",
                    "        context.user_data.pop('awaiting', None)",
                    "        from app.services import market as market_svc",
                    "        key = awaiting[4:]",
                    "        if key in ('coupon_apply', 'apply_coupon', 'redeem_gift'):",
                    "            await message.reply_text(market_svc.apply_coupon(text.strip(), user.id) if hasattr(market_svc, 'apply_coupon') else market_svc.coupon_apply_code(user.id, text.strip(), 0))",
                    "            return",
                    "        if key in ('wallet_topup', 'topup'):",
                    "            await message.reply_text(",
                    "                '⚠️ الشحن المجاني متوقف. استخدم /buy أو /vfcash'",
                    "            )",
                    "            return",
                    "        if 'transfer' in key:",
                    "            parts = text.split()",
                    "            if len(parts) < 2:",
                    "                await message.reply_text('الصيغة: user_id amount')",
                    "                return",
                    "            try:",
                    "                to_uid, amt = int(parts[0]), int(parts[1])",
                    "                if amt <= 0:",
                    "                    await message.reply_text('مبلغ غير صالح')",
                    "                    return",
                    "                if not market_svc.wallet_debit(user.id, amt, note='transfer_out'):",
                    "                    await message.reply_text('رصيد غير كافٍ')",
                    "                    return",
                    "                bal = market_svc.wallet_add(to_uid, amt)",
                    "                await message.reply_text('تم التحويل. رصيد المستلم: ' + str(bal))",
                    "            except (TypeError, ValueError):",
                    "                await message.reply_text('صيغة غير صحيحة')",
                    "            return",
                    "        await message.reply_text('تم: ' + text[:100])",
                    "        return",
                ]
                if need_market
                else []
            ),
            # Optional services — only when imported (need_* flags)
            *(
                [
                    "    if awaiting == 'task_title':",
                    "        tasks_svc.add_task(user.id, message.text.strip())",
                    "        context.user_data.pop('awaiting', None)",
                    "        await message.reply_text('تمت إضافة المهمة')",
                    "        return",
                ]
                if need_tasks
                else []
            ),
            *(
                [
                    "    if awaiting == 'note_body':",
                    "        notes_svc.add_note(user.id, message.text.strip())",
                    "        context.user_data.pop('awaiting', None)",
                    "        await message.reply_text('تمت إضافة الملاحظة')",
                    "        return",
                ]
                if need_notes
                else []
            ),
            *(
                [
                    "    if awaiting == 'reminder_body':",
                    "        chat_id = chat.id if chat is not None else user.id",
                    "        rid = reminders_svc.set_reminder(user.id, message.text.strip(), chat_id=chat_id)",
                    "        context.user_data.pop('awaiting', None)",
                    "        await message.reply_text(f'تم ضبط التذكير #{rid}')",
                    "        return",
                ]
                if need_reminders
                else []
            ),
            *(
                [
                    "    if awaiting == 'welcome_message' and chat is not None:",
                    "        welcome_svc.set_message(chat.id, message.text.strip())",
                    "        context.user_data.pop('awaiting', None)",
                    "        await message.reply_text('تم حفظ رسالة الترحيب')",
                    "        return",
                ]
                if need_welcome
                else []
            ),
            *(
                [
                    "    if awaiting == 'ticket_subject':",
                    "        tid = tickets_svc.open_ticket(user.id, message.text.strip(), chat.id if chat else 0)",
                    "        context.user_data.pop('awaiting', None)",
                    "        await message.reply_text(f'تم فتح التذكرة #{tid}')",
                    "        return",
                ]
                if need_tickets
                else []
            ),
            *(
                [
                    "    if awaiting == 'sec_phish':",
                    "        rid = security_svc.report(user.id, 'phish', message.text.strip())",
                    "        context.user_data.pop('awaiting', None)",
                    "        await message.reply_text(f'تم تسجيل بلاغ التصيد #{rid}')",
                    "        return",
                    "    if awaiting == 'sec_incident':",
                    "        rid = security_svc.report(user.id, 'incident', message.text.strip())",
                    "        context.user_data.pop('awaiting', None)",
                    "        await message.reply_text(f'تم تسجيل البلاغ الأمني #{rid}')",
                    "        return",
                ]
                if need_security
                else []
            ),
            "",
            "    # Guaranteed final response: ordinary text must never disappear silently.",
            "    await message.reply_text('تم استلام رسالتك: ' + message.text[:200])",
            "",
            *(
                [
                    "async def photo_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
                    "    message = update.effective_message",
                    "    user = update.effective_user",
                    "    if message is None or user is None or not message.photo:",
                    "        return",
                    "    awaiting = context.user_data.get('awaiting')",
                    "    try:",
                    "        from app.services import generic as generic_svc",
                    "        caption = (message.caption or '').strip()",
                    "        photo = message.photo[-1]",
                    "        path = ''",
                    "        try:",
                    "            tg_file = await context.bot.get_file(photo.file_id)",
                    "            path = f'/tmp/ocr_{user.id}_{photo.file_id}.jpg'",
                    "            await tg_file.download_to_drive(path)",
                    "        except Exception as _dl_exc:",
                    "            import logging as _logging",
                    "            _logging.getLogger(__name__).debug('ocr download: %s', _dl_exc)",
                    "            path = ''",
                    "        if path and hasattr(generic_svc, 'ocr_from_image'):",
                    "            result = generic_svc.ocr_from_image(user.id, path, caption)",
                    "        else:",
                    "            result = getattr(generic_svc, 'ocr_hint', lambda *a, **k: 'تم استلام الصورة.')(user.id, caption or 'photo_received')",
                    "        if awaiting == 'ocr_photo':",
                    "            context.user_data.pop('awaiting', None)",
                    "        await message.reply_text(str(result))",
                    "    except Exception as _ocr_exc:",
                    "        import logging as _logging",
                    "        _logging.getLogger(__name__).warning('ocr failed: %s', _ocr_exc)",
                    "        await message.reply_text('تم استلام الصورة.')",
                    "",
                ]
                if (need_ocr or need_market)
                else []
            ),
            "async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    if getattr(context, 'user_data', None) is not None:",
            "        context.user_data.pop('awaiting', None)",
            "        context.user_data.pop('flow', None)",
            "    if message is not None:",
            "        await message.reply_text('تم إلغاء العملية الحالية.')",
            "",
            "",
        ]

    if need_welcome:
        lines += [
            "async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    result = update.chat_member or update.my_chat_member",
            "    if result is None:",
            "        return",
            "    old = result.old_chat_member.status if result.old_chat_member else ''",
            "    new = result.new_chat_member.status if result.new_chat_member else ''",
            "    if new not in {'member', 'restricted'} or old in {'member', 'restricted', 'administrator', 'creator'}:",
            "        return",
            "    user = result.new_chat_member.user if result.new_chat_member else None",
            "    chat = result.chat",
            "    if user is None or user.is_bot:",
            "        return",
            "    text = welcome_svc.format_welcome(chat.id, user.full_name or user.first_name or 'عضو')",
            "    if text:",
            "        await context.bot.send_message(chat_id=chat.id, text=text)",
            "",
            "",
        ]


    # Callback feature handlers (must exist — callback_router awaits them)
    for feat in spec.features:
        if feat.trigger.type != "callback":
            continue
        fname = f"handle_{feat.id}".replace("-", "_")
        if fname in emitted_fnames:
            continue
        emitted_fnames.add(fname)
        # Prefer reusing the command handler for the same feature key
        cmd_peer = None
        for f2 in spec.features:
            if f2.trigger.type == "command" and f2.feature == feat.feature:
                cmd_peer = f"handle_{f2.id}".replace("-", "_")
                break
        lines.append(f"async def {fname}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
        if cmd_peer and cmd_peer in emitted_fnames:
            lines.append(f"    await {cmd_peer}(update, context)")
        else:
            lines.append("    message = update.effective_message")
            lines.append("    query = update.callback_query")
            lines.append("    if query is not None:")
            lines.append("        try:")
            lines.append("            await query.answer()")
            lines.append("        except Exception:")
            lines.append("            pass")
            lines.append("    if message is not None:")
            label = {
                "task_add": "إضافة مهمة", "task_list": "مهامي", "task_delete": "حذف مهمة",
                "task_done": "إنهاء مهمة", "task_clear": "مسح المنتهية",
                "remind_set": "تذكير", "remind_list": "تذكيراتي",
                "note_add": "ملاحظة", "note_list": "ملاحظاتي",
                "lang": "اللغة", "help": "مساعدة", "start": "ابدأ",
            }.get(feat.feature or "", (feat.feature or feat.trigger.id or "action").replace("_", " "))
            lines.append(f"        await message.reply_text({label!r})")
        lines.append("")


    if need_mod:
        lines += [
            "async def anti_abuse_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    chat = update.effective_chat",
            "    user = update.effective_user",
            "    if message is None or chat is None or user is None:",
            "        return",
            "    if chat.type not in {'group', 'supergroup'}:",
            "        return",
            "    # skip admins",
            "    try:",
            "        member = await context.bot.get_chat_member(chat.id, user.id)",
            "        if member.status in {'creator', 'administrator'}:",
            "            return",
            "    except Exception:",
            "        pass",
            "    text = message.text or message.caption or ''",
            "    settings = moderation_svc.get_settings(chat.id) if hasattr(moderation_svc, 'get_settings') else {'anti_link': 1, 'anti_spam': 1}",
            "    bad = False",
            "    if settings.get('anti_link') and hasattr(moderation_svc, 'looks_like_link') and moderation_svc.looks_like_link(text):",
            "        bad = True",
            "    if settings.get('anti_spam') and hasattr(moderation_svc, 'looks_like_spam') and moderation_svc.looks_like_spam(text):",
            "        bad = True",
            "    if not bad:",
            "        return",
            "    try:",
            "        await message.delete()",
            "        await context.bot.send_message(chat.id, f'تم حذف رسالة مخالفة من {user.id} (روابط/سبام)')",
            "        if hasattr(moderation_svc, 'log_action'):",
            "            moderation_svc.log_action(chat.id, 0, 'auto_delete', user.id, 'link_or_spam')",
            "    except Exception:",
            "        pass",
            "",
            "",
        ]


    # callback router
    cb_map: list[tuple[str, str]] = []
    for feat in spec.features:
        if feat.trigger.type == "callback":
            cb_map.append((feat.trigger.id, f"handle_{feat.id}".replace("-", "_")))

    # Build command → handler map so inline buttons actually run logic
    cmd_to_handler: list[tuple[str, str]] = []
    for feat in spec.features:
        if feat.trigger.type != "command":
            continue
        if feat.feature in ("start", "help") or feat.trigger.id in ("start", "help"):
            continue
        h = f"handle_{feat.id}".replace("-", "_")
        cmd_to_handler.append((feat.trigger.id, h))
        slug2 = feat.feature.lower().replace("_", "")
        if slug2 and slug2 != feat.trigger.id:
            cmd_to_handler.append((slug2, h))



    # Menu handlers ONLY for services present in this bot (avoids ModuleNotFoundError)
    available_services: set[str] = set()
    for feat in spec.features:
        cap = get_capability(feat.feature)
        if cap:
            available_services.add(cap.service)

    menu_lines: list[str] = []
    menu_routes: list[tuple[str, str]] = []

    if "shop" in available_services or "cart" in available_services or "payments" in available_services:
        menu_lines += [
            "async def menu_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    if message is None:",
            "        return",
            "    from app.services import market as market_svc",
            "    await message.reply_text('【 المتجر 】' + chr(10) + market_svc.catalog())",
            "",
            "async def menu_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    if message is None or user is None:",
            "        return",
            "    from app.services import market as market_svc",
            "    await message.reply_text('【 السلة 】' + chr(10) + str(market_svc.cart_view(user.id)))",
            "",
            "async def menu_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    if message is None or user is None:",
            "        return",
            "    from app.services import market as market_svc",
            "    items = market_svc.my_orders(user.id) if hasattr(market_svc, 'my_orders') else []",
            "    body = chr(10).join(str(x) for x in items) if items else 'لا طلبات بعد'",
            "    await message.reply_text('【 طلباتي 】' + chr(10) + body)",
            "",
        ]
        menu_routes += [
            ("shopcatalog", "menu_shop"),
            ("cartview", "menu_cart"),
            ("orders", "menu_orders"),
        ]

    if "points" in available_services:
        menu_lines += [
            "async def menu_points(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    if message is None or user is None:",
            "        return",
            "    from app.services import market as market_svc",
            "    await message.reply_text('【 النقاط 】' + chr(10) + 'رصيدك: ' + str(market_svc.points_balance(user.id)))",
            "",
        ]
        menu_routes.append(("points", "menu_points"))

    if "subscriptions" in available_services:
        menu_lines += [
            "async def menu_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    if message is None:",
            "        return",
            "    from app.services import market as market_svc",
            "    plans = market_svc.list_plans() if hasattr(market_svc, 'list_plans') else []",
            "    body = chr(10).join(str(p) for p in plans) if plans else 'لا خطط بعد'",
            "    await message.reply_text('【 الخطط 】' + chr(10) + body)",
            "",
        ]
        menu_routes.append(("plans", "menu_plans"))

    if "wallet" in available_services:
        menu_lines += [
            "async def menu_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    if message is None or user is None:",
            "        return",
            "    from app.services import market as market_svc",
            "    bal = market_svc.wallet_balance(user.id) if hasattr(market_svc, 'wallet_balance') else 0",
            "    await message.reply_text('【 المحفظة 】' + chr(10) + 'الرصيد: ' + str(bal))",
            "",
        ]
        menu_routes.append(("balance", "menu_balance"))

    if "contests" in available_services:
        menu_lines += [
            "async def menu_contests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    if message is None:",
            "        return",
            "    await message.reply_text('【 المسابقات 】')",
            "",
        ]
        menu_routes.append(("contests", "menu_contests"))

    if "tickets" in available_services:
        menu_lines += [
            "async def menu_ticket_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    if message is None:",
            "        return",
            "    await message.reply_text('【 فتح تذكرة 】 أرسل وصف المشكلة.')",
            "",
            "async def menu_ticket_my(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    if message is None:",
            "        return",
            "    await message.reply_text('【 تذاكري 】')",
            "",
        ]
        menu_routes += [("ticket_open", "menu_ticket_open"), ("ticket_my", "menu_ticket_my")]

    lines.extend(menu_lines)


    lines.append("async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    query = update.callback_query")
    lines.append("    if query is None:")
    lines.append("        return")
    lines.append("    data = query.data or ''")
    if need_market or need_tickets:
        lines.append("    # Flow engine callbacks (choice / confirm / cancel / back)")
        lines.append("    if data.startswith('flow:'):")
        lines.append("        try:")
        lines.append("            from app.flow_engine import handle_callback as _flow_cb")
        lines.append("            if await _flow_cb(update, context):")
        lines.append("                return")
        lines.append("        except Exception:")
        lines.append("            pass")
    lines.append("    await query.answer()")
    lines.append("    if data.startswith('cmd:'):")
    lines.append("        cmd = (data[4:] or '').strip().lower().replace('-', '_').replace('.', '')")
    lines.append("        cmd_compact = cmd.replace('_', '').replace(' ', '')")
    lines.append("        _CMD_MAP = {")
    seen_map: set[str] = set()
    for cmd, h in cmd_to_handler:
        for key in {cmd.lower(), cmd.lower().replace("_", ""), "".join(c for c in cmd.lower() if c.isalnum())}:
            if not key or key in seen_map:
                continue
            seen_map.add(key)
            lines.append(f"            {key!r}: {h},")
    # Only register menu routes that were actually emitted (no key overwrite)
    for _mk, _mh in menu_routes:
        if _mk in seen_map:
            continue
        seen_map.add(_mk)
        lines.append(f"            {_mk!r}: {_mh},")
    if "lang" not in seen_map:
        lines.append("            'lang': help_handler,")
    lines.append("        }")
    lines.append("        _ALIASES = {")
    lines.append("            'language': 'lang',")
    if need_market:
        lines.append("            'shop': 'shopcatalog', 'catalog': 'shopcatalog', 'cart': 'cartview',")
        lines.append("            'orders': 'shopmyorders', 'myorders': 'shopmyorders',")
        lines.append("            'wallet': 'walletbalance', 'coupon': 'couponapply', 'buy': 'shopbuy',")
        lines.append("            'plans': 'plans', 'sub': 'plans', 'subs': 'plans', 'leaderboard': 'leaderboard',")
        lines.append("            'points': 'pointsbalance', 'balance': 'walletbalance',")
    if need_tickets:
        lines.append("            'support': 'ticketopen', 'ticket': 'ticketopen',")
    lines.append("        }")
    lines.append("        fn = _CMD_MAP.get(cmd) or _CMD_MAP.get(cmd_compact)")
    lines.append("        if fn is None:")
    lines.append("            target = _ALIASES.get(cmd) or _ALIASES.get(cmd_compact)")
    lines.append("            if target:")
    lines.append("                fn = _CMD_MAP.get(target) or _CMD_MAP.get(target.replace('_', ''))")
    lines.append("        if fn is not None:")
    lines.append("            await fn(update, context)")
    lines.append("            return")
    lines.append("        # Last-chance: fuzzy match handler name")
    lines.append("        import sys as _sys")
    lines.append("        mod = _sys.modules[__name__]")
    lines.append("        for attr in dir(mod):")
    lines.append("            if not attr.startswith('handle_'):")
    lines.append("                continue")
    lines.append("            compact = attr[7:].replace('_', '').lower()")
    lines.append("            if compact == cmd_compact or cmd_compact in compact:")
    lines.append("                await getattr(mod, attr)(update, context)")
    lines.append("                return")
    lines.append("        message = update.effective_message")
    lines.append("        if message is not None:")
    lines.append("            await message.reply_text(")
    lines.append("                'الأمر غير مربوط حالياً: /' + (data[4:] or '') + chr(10) + 'جرّب /help أو /start'")
    lines.append("            )")
    lines.append("        return")
    if cb_map:
        for cid, handler in cb_map:
            lines.append(f"    if data == {cid!r}:")
            lines.append(f"        await {handler}(update, context)")
            lines.append("        return")
    lines.append("    if data in {'i18n.lang', 'lang', 'language'}:")
    lines.append("        await handle_lang(update, context)")
    lines.append("        return")
    lines.append("    message = update.effective_message")
    lines.append("    if message is not None:")
    lines.append("        await message.reply_text(data)")
    lines.append("")


    # Telegram Payments: pre-checkout + successful_payment (never fake-paid)
    need_pay = any(
        (get_capability(f.feature) and get_capability(f.feature).service in {"shop", "payments", "cart", "subscriptions"})  # type: ignore
        for f in spec.features
    )
    if need_pay:
        lines += [
            "async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    query = update.pre_checkout_query",
            "    if query is None:",
            "        return",
            "    from app.services import market as market_svc",
            "    oid = market_svc.parse_order_payload(query.invoice_payload or '')",
            "    order = market_svc.get_order(oid) if oid else None",
            "    if not order or order.get('status') != 'pending':",
            "        await query.answer(ok=False, error_message='Order unavailable')",
            "        return",
            "    if int(order['amount_cents']) != int(query.total_amount):",
            "        await query.answer(ok=False, error_message='Amount mismatch')",
            "        return",
            "    await query.answer(ok=True)",
            "",
            "",
            "async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    if message is None or user is None or message.successful_payment is None:",
            "        return",
            "    sp = message.successful_payment",
            "    from app.services import market as market_svc",
            "    text = market_svc.fulfill_successful_payment(",
            "        user.id, sp.invoice_payload or '', sp.telegram_payment_charge_id or '',",
            "    )",
            "    await message.reply_text(text)",
            "",
            "",
        ]

    return "\n".join(lines) + "\n"


