"""Emit handlers, keyboards, main.py registration for generated bots."""
from __future__ import annotations

from ..coding_emit_foundation import _msg
from ..registry import get_capability
from ..schema import BotSpec, Feature

def _market_handler_lines(cap, ok: str, fail: str) -> list[str]:
    """Map capability service.method → real market.py calls (no empty success)."""
    svc = cap.service
    method = cap.method
    L: list[str] = ["    from app.services import market as market_svc"]

    def need_args(min_n: int = 1, prompt: str | None = None, await_key: str | None = None) -> None:
        """If args missing (e.g. button press), ask user and set conversation state."""
        key = await_key or f"mkt_{method}"
        prompts = {
            "coupon_apply": "أرسل كود الكوبون الآن — Send coupon code now",
            "apply_coupon": "أرسل كود الكوبون الآن — Send coupon code now",
            "redeem_gift": "أرسل كود الهدية — Send gift code",
            "wallet_topup": "أرسل مبلغ الشحن (رقم) — Send top-up amount",
            "topup": "أرسل مبلغ الشحن (رقم) — Send top-up amount",
            "transfer": "أرسل: user_id المبلغ — Send: user_id amount",
            "stock_set": "أرسل: product_id الكمية — Send: product_id qty",
            "grant_points": "أرسل: user_id النقاط — Send: user_id points",
            "broadcast_segment": "أرسل نص الإذاعة — Send broadcast text",
        }
        msg = prompt or prompts.get(method, "أرسل المطلوب كرسالة تالية — Send required input next")
        L.append(f"    if not context.args or len(context.args) < {min_n}:")
        L.append(f"        context.user_data['awaiting'] = {key!r}")
        L.append(f"        await message.reply_text({msg!r})")
        L.append("        return")

    # ── catalog / products ────────────────────────────────────────────
    if method in {"search", "product_search"}:
        L += [
            "    q = ' '.join(context.args) if context.args else ''",
            "    if hasattr(market_svc, 'product_search'):",
            "        text = market_svc.product_search(q)",
            "    else:",
            "        text = market_svc.catalog()",
            "    await message.reply_text(text)",
        ]
    elif method in {"product_info", "info"}:
        L += [
            "    if not context.args:",
            "        await message.reply_text('Usage: /productinfo <product_id>')",
            "        return",
            "    try:",
            "        pid = int(context.args[0])",
            "    except ValueError:",
            "        await message.reply_text('رقم منتج غير صالح')",
            "        return",
            "    if hasattr(market_svc, 'product_info'):",
            "        text = market_svc.product_info(pid)",
            "    else:",
            "        text = market_svc.catalog()",
            "    await message.reply_text(text)",
        ]
    elif method in {"catalog", "list_content", "flash_list", "recommend"}:
        L.append("    cat = market_svc.catalog()")
        L.append("    text = '【 المتجر 】' + chr(10) + cat + chr(10)+chr(10) + 'أضف للسلة: /cartadd <id> — أو افتح السلة من القائمة'")
        L.append("    await message.reply_text(text)")
    elif method in {"add_item", "upload"}:
        L += [
            "    # Admin/staff only — product create",
            "    if not market_svc.role_require(user.id, 'staff'):",
            "        await message.reply_text('❌ غير مصرح — للأدمن فقط')",
            "        return",
            "    # Multi-step wizard (name → price → category → desc → photo → confirm)",
            "    if context.args:",
            "        pid = market_svc.add_item(user.id, ' '.join(context.args))",
            "        if not pid:",
            "            await message.reply_text('❌ فشل الإضافة أو غير مصرح')",
            "            return",
            "        await message.reply_text(f'Product added #{pid}')",
            "        return",
            "    try:",
            "        from app.flow_engine import start_flow",
            "        await start_flow(update, context, 'add_product')",
            "    except Exception:",
            "        await message.reply_text('Usage: /addproduct Title|price_cents  e.g. Book|999')",
        ]
    elif method in {"stock_set"}:
        L += [
            "    if not market_svc.role_require(user.id, 'staff'):",
            "        await message.reply_text('❌ غير مصرح — للأدمن فقط')",
            "        return",
            "    if not context.args:",
            "        await message.reply_text('Usage: /stock product_id qty')",
            "        return",
            "    # stock_set should use dedicated API when available",
            "    try:",
            "        parts = context.args",
            "        pid, qty = int(parts[0]), int(parts[1])",
            "        msg = market_svc.stock_set(user.id, pid, qty) if hasattr(market_svc, 'stock_set') else 'use admin panel'",
            "        await message.reply_text(str(msg))",
            "    except Exception:",
            "        await message.reply_text('Usage: /stock product_id qty')",
        ]
    elif method == "checkout" and svc == "cart":
        L += [
            "    summary = market_svc.cart_checkout(user.id)",
            "    await message.reply_text(summary)",
            "    try:",
            "        from app.flow_engine import start_flow",
            "        await start_flow(update, context, 'pay_methods')",
            "    except Exception:",
            "        await message.reply_text(",
            "            'ادفع عبر: /pay (اختيار الطريقة) أو /vfcash أو /buy'",
            "        )",
        ]
    elif method in {"place_order", "send_invoice", "checkout", "buy"}:
        L += [
            "    arg = ' '.join(context.args) if context.args else '1'",
            "    oid = market_svc.place_order(user.id, arg)",
            "    if not oid:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    order = market_svc.get_order(oid)",
            "    from app.config import get_settings",
            "    settings = get_settings()",
            "    if not settings.payment_provider_token or not order:",
            f"        await message.reply_text({ok!r} + f' order #{{oid}} (set PAYMENT_PROVIDER_TOKEN to invoice)')",
            "        return",
            "    prod = market_svc.get_product(int(order['product_id']))",
            "    title = (prod or {}).get('title') or f'Order #{oid}'",
            "    from telegram import LabeledPrice",
            "    await context.bot.send_invoice(",
            "        chat_id=message.chat_id,",
            "        title=str(title)[:32],",
            "        description=f'Order #{oid}'[:255],",
            "        payload=market_svc.invoice_payload_for_order(oid),",
            "        provider_token=settings.payment_provider_token,",
            "        currency=str(order.get('currency') or settings.default_currency),",
            "        prices=[LabeledPrice(str(title)[:32], int(order['amount_cents']))],",
            "    )",
        ]
    elif method in {"wallet_topup", "topup"}:
        L += [
            "    # Free top-up disabled — redirect to real payment rails",
            "    await message.reply_text(",
            "        '⚠️ الشحن المجاني متوقف.' + chr(10) +",
            "        'ادفع عبر: /buy (Telegram Payments) أو /vfcash (فودافون كاش + موافقة أدمن)' + chr(10) +",
            "        'الرصيد الحالي: ' + str(market_svc.wallet_balance(user.id))",
            "    )",
        ]
    elif method in {"vodafone", "vfcash", "vodafone_cash"}:
        L += [
            "    try:",
            "        from app.flow_engine import start_flow",
            "        await start_flow(update, context, 'vodafone_cash')",
            "    except Exception:",
            "        await message.reply_text('استخدم /vfcash لبدء دفع فودافون كاش')",
        ]
    elif method in {"methods", "pay_methods"}:
        L += [
            "    try:",
            "        from app.flow_engine import start_flow",
            "        await start_flow(update, context, 'pay_methods')",
            "    except Exception:",
            "        await message.reply_text(",
            "            'طرق الدفع المتاحة:' + chr(10) +",
            "            '• Telegram Payments — /buy أو /cartcheckout' + chr(10) +",
            "            '• فودافون كاش — /vfcash' + chr(10) +",
            "            '• المحفظة — /topup و /balance'",
            "        )",
        ]
    elif method in {"history"} and svc == "wallet":
        L += [
            "    await message.reply_text(market_svc.wallet_history(user.id) if hasattr(market_svc, 'wallet_history') else str(market_svc.wallet_balance(user.id)))",
        ]
    elif method in {"balance"} and svc == "wallet":
        L += [
            "    bal = market_svc.wallet_balance(user.id)",
            "    await message.reply_text('رصيد المحفظة: ' + str(bal))",
        ]
    elif method in {"list_orders"}:
        L += [
            "    # Staff sees all; others only own orders (no IDOR)",
            "    if market_svc.role_require(user.id, 'staff'):",
            "        items = market_svc.list_orders(admin_id=user.id)",
            "    else:",
            "        items = market_svc.list_orders(user_id=user.id)",
            "    await message.reply_text(market_svc.format_orders(items) if hasattr(market_svc, 'format_orders') else (",
            "        chr(10).join(f\"#{i['id']} {i['status']} {i['amount_cents']}\" for i in items) if items else 'No orders'",
            "    ))",
        ]
    elif method in {"my_orders"}:
        L += [
            "    items = market_svc.my_orders(user.id)",
            "    await message.reply_text(",
            "        chr(10).join(f\"#{i['id']} {i['status']}\" for i in items) if items else 'No orders'",
            "    )",
        ]
    elif method in {"cancel_order"}:
        L += [
            "    if not context.args:",
            "        await message.reply_text('Usage: /ordercancel <order_id>')",
            "        return",
            "    try:",
            "        oid = int(context.args[0])",
            "    except ValueError:",
            "        await message.reply_text('order_id must be a number')",
            "        return",
            "    ok_c = market_svc.cancel_order(user.id, oid)",
            "    await message.reply_text(f'Order #{oid} cancelled' if ok_c else f'Cannot cancel #{oid} — not found or not pending')",
        ]
    elif method in {"track_order"}:
        need_args(1)
        L += [
            "    try:",
            "        oid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.track_order(user.id, oid))",
        ]
    elif method in {"coupon_apply", "redeem_gift", "apply_coupon"}:
        need_args(1)
        L.append("    pct = market_svc.apply_coupon(context.args[0], user_id=user.id)")
        L.append("    await message.reply_text(f'Discount: {pct}%' if pct else 'Invalid or already used')")
    elif method in {"coupon_create", "create_coupon", "create_gift"}:
        need_args(2)
        L += [
            "    if not market_svc.role_require(user.id, 'staff'):",
            "        await message.reply_text('❌ غير مصرح — للأدمن فقط')",
            "        return",
            "    try:",
            "        code, pct = context.args[0], int(context.args[1])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    made = market_svc.create_coupon(code, pct, admin_id=user.id)",
            f"    await message.reply_text(({ok!r} + ' ' + made) if made else {fail!r})",
        ]
    # ── cart ──────────────────────────────────────────────────────────
    elif method in {"add", "cart_add"} and svc in {"cart", "shop"}:
        L += [
            "    if not context.args:",
            "        await message.reply_text(t('usage_cart_add') + chr(10) + market_svc.catalog())",
            "        return",
            "    try:",
            "        pid = int(context.args[0])",
            "        qty = int(context.args[1]) if len(context.args) > 1 else 1",
            "    except ValueError:",
            f"        await message.reply_text({fail!r} + ' — Usage: /cartadd <product_id> [qty]')",
            "        return",
            "    ok_c = market_svc.cart_add(user.id, pid, qty)",
            "    await message.reply_text(f'Added product #{pid} x{qty} to cart' if ok_c else 'Product not found — try /shop')",
        ]
    elif method in {"view", "view_cart"} and svc in {"cart", "shop"}:
        L.append("    await message.reply_text(market_svc.cart_view(user.id))")
    elif method in {"clear", "cart_clear"} and svc in {"cart", "shop"}:
        L.append("    n = market_svc.cart_clear(user.id)")
        L.append("    await message.reply_text(f'Cleared {n} items')")
    # ── points ────────────────────────────────────────────────────────
    elif method == "balance" and svc == "wallet":
        L.append("    bal = market_svc.wallet_balance(user.id)")
        L.append("    await message.reply_text('【 المحفظة 】' + chr(10) + f'الرصيد: {bal}' + chr(10)+chr(10) + 'شحن: /wallettopup — تحويل: /wallettransfer')")
    elif method == "balance" or (method == "history" and svc == "points"):
        if method == "history":
            L.append("    bal = market_svc.points_balance(user.id)")
            L.append("    await message.reply_text(f'Points balance: {bal}')")
        else:
            L.append("    await message.reply_text(f'Points: {market_svc.points_balance(user.id)}')")
    elif method == "leaderboard":
        L += [
            "    rows = market_svc.leaderboard()",
            "    text = chr(10).join(f'{i+1}. {u}: {b}' for i, (u, b) in enumerate(rows)) if rows else 'لا يوجد متصدرون بعد — اكسب نقاط أولاً'",
            "    await message.reply_text(text)",
        ]
    elif method in {"grant"} and svc == "points":
        need_args(2)
        L += [
            "    if not market_svc.role_require(user.id, 'staff'):",
            "        await message.reply_text('❌ غير مصرح — للأدمن فقط')",
            "        return",
            "    try:",
            "        uid, amt = int(context.args[0]), int(context.args[1])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    market_svc.points_credit(uid, amt, 'admin_grant', actor_id=user.id)",
            f"    await message.reply_text({ok!r})",
        ]
    elif method in {"debit", "redeem"}:
        need_args(1)
        L += [
            "    try:",
            "        if len(context.args) >= 2:",
            "            uid, amt = int(context.args[0]), int(context.args[1])",
            "        else:",
            "            uid, amt = user.id, int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    ok_d = market_svc.points_debit(uid, amt, 'redeem')",
            "    await message.reply_text(f'Redeemed {amt} points' if ok_d else 'Insufficient points')",
        ]
    elif method == "transfer" and svc == "wallet":
        need_args(2)
        L += [
            "    try:",
            "        to_uid, amt = int(context.args[0]), int(context.args[1])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    if amt <= 0:",
            "        await message.reply_text('مبلغ غير صالح')",
            "        return",
            "    if not market_svc.wallet_debit(user.id, amt, note='transfer_out'):",
            "        await message.reply_text('رصيد غير كافٍ')",
            "        return",
            "    bal = market_svc.wallet_add(to_uid, amt)",
            "    await message.reply_text(f'Transferred. Target wallet={bal}')",
        ]
    elif method == "transfer" and svc == "points":
        need_args(2)
        L += [
            "    try:",
            "        to_uid, amt = int(context.args[0]), int(context.args[1])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    if not market_svc.points_debit(user.id, amt, f'transfer_to_{to_uid}'):",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    market_svc.points_credit(to_uid, amt, f'transfer_from_{user.id}')",
            f"    await message.reply_text({ok!r})",
        ]
    # ── subscriptions ─────────────────────────────────────────────────
    elif method in {"list_plans", "compare_plans"}:
        L += [
            "    plans = market_svc.list_plans()",
            "    text = chr(10).join(",
            "        f\"#{p['id']} {p['name']} {p['price_cents']/100:.2f}\"",
            "        for p in plans",
            "    )",
            "    await message.reply_text(text or 'No plans')",
        ]
    elif method in {"my_subscription", "trial_status"}:
        L.append("    await message.reply_text(market_svc.my_subscription(user.id))")
    elif method in {"subscribe", "grant", "renew", "start_trial", "gift"} and svc == "subscriptions":
        if method == "start_trial":
            L.append("    await message.reply_text(market_svc.start_trial(user.id))")
        else:
            L.append("    if not context.args:")
            L.append("        plans = market_svc.list_plans()")
            L.append("        text = chr(10).join('#' + str(p['id']) + ' ' + str(p['name']) for p in plans)")
            L.append("        await message.reply_text('Usage: /subscribe <plan_id>' + chr(10) + text)")
            L.append("        return")
            L.append("    try:")
            L.append("        plan_id = int(context.args[0])")
            L.append("        target = int(context.args[1]) if len(context.args) > 1 else user.id")
            L.append("    except ValueError:")
            L.append("        await message.reply_text('plan_id must be a number — try /plans')")
            L.append("        return")
            L.append("    if target != user.id and not market_svc.role_require(user.id, 'staff'):")
            L.append("        await message.reply_text('❌ منح اشتراك لمستخدم آخر — للأدمن فقط')")
            L.append("        return")
            L.append("    # Self-subscribe still requires payment rails in production; free grant = staff only")
            L.append("    if not market_svc.role_require(user.id, 'staff'):")
            L.append("        await message.reply_text('اشترك عبر /buy أو /pay — المنح المجاني متوقف')")
            L.append("        return")
            L.append("    ok_g = market_svc.grant_sub(target, plan_id, actor_id=user.id)")
            L.append("    await message.reply_text((f'Subscription granted plan={plan_id}') if ok_g else 'Plan not found or unauthorized')")
    elif method == "revoke" and svc == "subscriptions":
        need_args(1)
        L += [
            "    try:",
            "        target = int(context.args[0])",
            "    except ValueError:",
            "        await message.reply_text('Usage: /revokesub <user_id>')",
            "        return",
            "    from app.services import generic as generic_svc",
            "    generic_svc.act('subscriptions', 'revoke', target, str(target))",
            "    await message.reply_text(f'Subscription revoke recorded for user {target}')",
        ]
    # ── contests ──────────────────────────────────────────────────────
    elif method in {"list_open", "rules", "share"}:
        L += [
            "    items = market_svc.list_contests()",
            "    text = chr(10).join(f\"#{c['id']} {c['title']}\" for c in items) if items else 'No open contests'",
            "    await message.reply_text(text)",
        ]
    elif method == "create" and svc == "contests":
        L.append("    title = ' '.join(context.args) if context.args else 'Contest'")
        L.append("    cid = market_svc.create_contest(title)")
        L.append(f"    await message.reply_text({ok!r} + f' #{{cid}}')")
    elif method == "join" and svc == "contests":
        need_args(1)
        L += [
            "    try:",
            "        cid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    joined = market_svc.join_contest(user.id, cid)",
            f"    await message.reply_text({ok!r} if joined else {fail!r})",
        ]
    elif method == "draw_winner":
        need_args(1)
        L += [
            "    if not market_svc.role_require(user.id, 'staff'):",
            "        await message.reply_text('❌ غير مصرح — للأدمن فقط')",
            "        return",
            "    try:",
            "        cid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    w = market_svc.draw_winner(cid, actor_id=user.id)",
            "    await message.reply_text(f'Winner user_id={w}' if w else 'No entries / unauthorized')",
        ]
    # ── growth / referrals ────────────────────────────────────────────
    elif method in {"my_code", "invite_link", "rewards_info", "stats", "achievements", "streak"}:
        if method in {"stats", "rewards_info", "achievements"}:
            L.append("    code = market_svc.referral_code(user.id)")
            L.append("    bal = market_svc.points_balance(user.id)")
            L.append("    await message.reply_text(f'Code: {code}\\nPoints: {bal}')")
        elif method == "streak":
            L.append("    await message.reply_text(market_svc.levels_for(user.id))")
        else:
            L.append("    code = market_svc.referral_code(user.id)")
            L.append("    await message.reply_text(f'Your code: {code}\\nShare: /start ref_{code}')")
    elif method in {"claim", "claim_reward"} and svc == "growth":
        need_args(1)
        L.append("    ok_c = market_svc.claim_referral(user.id, context.args[0])")
        L.append(f"    await message.reply_text({ok!r} if ok_c else 'Invalid or already-used referral code')")
    elif method == "daily_checkin":
        L.append("    await message.reply_text(market_svc.daily_checkin(user.id))")
    # ── wallet ────────────────────────────────────────────────────────
    elif method == "topup":
        need_args(1)
        L += [
            "    try:",
            "        amount = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    bal = market_svc.wallet_add(user.id, amount)",
            "    await message.reply_text(f'Wallet: {bal}')",
        ]
    elif method == "history" and svc == "wallet":
        L.append("    bal = market_svc.wallet_balance(user.id)")
        L.append("    await message.reply_text('【 المحفظة 】' + chr(10) + f'الرصيد: {bal}' + chr(10)+chr(10) + 'شحن: /wallettopup — تحويل: /wallettransfer')")
    elif method == "history" and svc == "payments":
        L.append("    await message.reply_text(market_svc.payment_history(user.id))")
    elif method == "receipt":
        need_args(1)
        L += [
            "    try:",
            "        pid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.payment_receipt(user.id, pid))",
        ]
    # ── i18n ──────────────────────────────────────────────────────────
    elif method in {"set_language", "auto_detect"}:
        # Prefer lightweight i18n module (no full market pack)
        L = ["    from app.services import i18n as lang_svc"]
        L.append("    if context.args:")
        L.append("        lang = context.args[0].lower()[:2]")
        L.append("    else:")
        L.append("        cur = lang_svc.get_lang(user.id)")
        L.append("        lang = 'ar' if str(cur).startswith('en') else 'en'")
        L.append("    new_lang = lang_svc.set_lang(user.id, lang)")
        L.append("    if new_lang.startswith('ar'):")
        L.append("        await message.reply_text('تم تغيير اللغة إلى العربية 🇸🇦 — أعد /start لتحديث القائمة')")
        L.append("    else:")
        L.append("        await message.reply_text('Language switched to English 🇬🇧 — Send /start to refresh the menu')")
    elif method == "start_trial":
        L.append("    await message.reply_text(market_svc.start_trial(user.id))")
    elif method == "level":
        L.append("    await message.reply_text(market_svc.levels_for(user.id))")
    # ── wishlist / reviews / shipping / refunds → durable generic ─────
    elif method in {"privacy", "privacy_policy"} or (svc == "compliance" and method == "privacy"):
        L.append("    await message.reply_text(")
        L.append("        'Privacy: We store Telegram user id, orders, and points locally in SQLite. '")
        L.append("        'No data is sold. Use /deleteme style flows if enabled to request deletion.'")
        L.append("    )")
    elif method in {"terms", "terms_of_service"} or (svc == "compliance" and method == "terms"):
        L.append("    await message.reply_text(")
        L.append("        'Terms: Digital goods are delivered after successful Telegram Payment. '")
        L.append("        'Abuse, fraud, or chargebacks may result in account restriction.'")
        L.append("    )")
    elif method == "wishlist_add":
        need_args(1)
        L += [
            "    try:",
            "        pid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.wishlist_add(user.id, pid))",
        ]
    elif method == "wishlist_view":
        L.append("    await message.reply_text(market_svc.wishlist_view(user.id))")
    elif method == "review_add":
        L.append("    await message.reply_text(market_svc.review_add(user.id, ' '.join(context.args) if context.args else ''))")
    elif method == "shipping_set":
        L.append("    await message.reply_text(market_svc.shipping_set(user.id, ' '.join(context.args) if context.args else ''))")
    elif method in {"refund_request", "refund_approve"}:
        need_args(1)
        L += [
            "    try:",
            "        oid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.refund_request(user.id, oid))",
        ]
    elif method == "digital_deliver":
        need_args(1)
        L += [
            "    try:",
            "        oid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.digital_deliver(user.id, oid))",
        ]
    elif method in {"pre_checkout", "successful_payment"}:
        L.append("    await message.reply_text('Payment events are handled automatically after invoice pay — no manual command needed.')")
    # ── Enterprise depth ────────────────────────────────────────────
    elif method in {"order_set_status", "set_status"} and svc in {"shop", "orders", "admin"}:
        need_args(2)
        L += [
            "    try:",
            "        oid = int(context.args[0]); st = context.args[1]",
            "    except Exception:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    note = ' '.join(context.args[2:]) if len(context.args) > 2 else ''",
            "    await message.reply_text(market_svc.order_set_status(oid, st, user.id, note))",
        ]
    elif method in {"order_timeline", "timeline"}:
        need_args(1)
        L += [
            "    try:",
            "        oid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.order_timeline(oid))",
        ]
    elif method in {"stock_adjust", "stock_set"}:
        need_args(2)
        L += [
            "    try:",
            "        pid = int(context.args[0]); delta = int(context.args[1])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.stock_adjust(pid, delta, user.id, ' '.join(context.args[2:])))",
        ]
    elif method in {"stock_low", "low_stock"}:
        L.append("    thr = int(context.args[0]) if context.args and context.args[0].isdigit() else 5")
        L.append("    await message.reply_text(market_svc.stock_low(thr))")
    elif method in {"coupon_create", "create_coupon"}:
        need_args(1)
        L += [
            "    if not market_svc.role_require(user.id, 'staff'):",
            "        await message.reply_text('❌ غير مصرح — للأدمن فقط')",
            "        return",
            "    await message.reply_text(market_svc.coupon_create(user.id, ' '.join(context.args)))",
        ]
    elif method in {"coupon_apply", "apply_coupon", "redeem_gift"}:
        need_args(1)
        L += [
            "    code = context.args[0]",
            "    oid = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 0",
            "    await message.reply_text(market_svc.coupon_apply_code(user.id, code, oid))",
        ]
    elif method in {"affiliate_register", "referral_code"} and svc in {"growth", "affiliate", "points"}:
        L.append("    parent = context.args[0] if context.args else ''")
        L.append("    await message.reply_text(market_svc.affiliate_register(user.id, parent))")
    elif method in {"affiliate_stats", "referral_stats"}:
        L.append("    await message.reply_text(market_svc.affiliate_stats(user.id))")
    elif method in {"affiliate_credit"}:
        need_args(1)
        L += [
            "    try: oid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.affiliate_credit_for_order(oid))",
        ]
    elif method in {"vendor_register", "vendor_create"}:
        L.append("    await message.reply_text(market_svc.vendor_register(user.id, ' '.join(context.args) or 'Vendor'))")
    elif method in {"vendor_list", "vendors"}:
        L.append("    await message.reply_text(market_svc.vendor_list())")
    elif method in {"vendor_attach", "vendor_product"}:
        need_args(2)
        L += [
            "    try:",
            "        vid = int(context.args[0]); pid = int(context.args[1])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.vendor_attach_product(vid, pid))",
        ]
    elif method in {"saas_create", "tenant_create", "workspace_create"}:
        L.append("    plan = context.args[-1] if context.args and context.args[-1].lower() in {'free','pro','enterprise'} else 'free'")
        L.append("    name = ' '.join(a for a in context.args if a.lower() not in {'free','pro','enterprise'}) or 'Workspace'")
        L.append("    await message.reply_text(market_svc.saas_create_tenant(user.id, name, plan))")
    elif method in {"saas_add_member", "tenant_add"}:
        need_args(2)
        L += [
            "    try:",
            "        tid = int(context.args[0]); uid = int(context.args[1])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    role = context.args[2] if len(context.args) > 2 else 'member'",
            "    await message.reply_text(market_svc.saas_add_member(tid, uid, role, actor_id=user.id))",
        ]
    elif method in {"saas_info", "tenant_info"}:
        need_args(1)
        L += [
            "    try: tid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.saas_tenant_info(tid))",
        ]
    elif method in {"invoice_create"}:
        need_args(1)
        L += [
            "    try: amount = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    oid = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 0",
            "    await message.reply_text(market_svc.invoice_create(user.id, amount, oid))",
        ]
    elif method in {"invoice_list", "invoices"}:
        L.append("    await message.reply_text(market_svc.invoice_list(user.id))")
    elif method in {"invoice_pay"}:
        need_args(1)
        L += [
            "    try: iid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    await message.reply_text(market_svc.invoice_pay(iid, user.id))",
        ]
    elif method == "lead_capture" and svc == "crm":
        L += [
            "    raw = ' '.join(context.args).strip()",
            "    if not raw:",
            "        await message.reply_text('أرسل بيانات العميل بهذا الشكل: الاسم | البريد | الهاتف')",
            "        return",
            "    from app.services import extras as extras_svc",
            "    lead_id = extras_svc.lead_capture(user.id, raw)",
            "    await message.reply_text(f'تم حفظ العميل المحتمل #{lead_id}')",
        ]
    elif method == "lead_list" and svc == "crm":
        L += [
            "    from app.services import extras as extras_svc",
            "    rows = extras_svc.lead_list()",
            "    if not rows:",
            "        await message.reply_text('لا يوجد عملاء مسجلون')",
            "        return",
            "    await message.reply_text('\\n'.join(f\"#{r.get('id')} {r.get('text', '')}\" for r in rows))",
        ]
    elif method in {"analytics_overview", "analytics_revenue", "dashboard", "stats"} and svc in {"analytics", "admin", "shop"}:
        L += [
            "    if not market_svc.role_require(user.id, 'staff'):",
            "        await message.reply_text('❌ Analytics — للأدمن فقط')",
            "        return",
            "    await message.reply_text(market_svc.analytics_dashboard(admin_id=user.id))",
        ]
    elif method in {"audit_tail", "audit_log"}:
        L += [
            "    if not market_svc.role_require(user.id, 'staff'):",
            "        await message.reply_text('❌ غير مصرح')",
            "        return",
            "    await message.reply_text(market_svc.audit_tail(20))",
        ]
    elif method in {"broadcast_segment"}:
        L += [
            "    if not market_svc.role_require(user.id, 'staff'):",
            "        await message.reply_text('❌ غير مصرح')",
            "        return",
            "    rule = context.args[0] if context.args else 'all'",
            "    await message.reply_text(market_svc.broadcast_segment_count(rule))",
        ]
    else:
        if svc in {"analytics", "admin", "notify"}:
            L += [
                "    from app.db import connect, init_db",
                "    init_db()",
                "    with connect() as conn:",
                "        products = conn.execute('SELECT COUNT(*) c FROM products').fetchone()['c']",
                "        orders = conn.execute('SELECT COUNT(*) c FROM orders').fetchone()['c']",
                "        paid = conn.execute(\"SELECT COUNT(*) c FROM orders WHERE status='paid'\").fetchone()['c']",
                "        users = conn.execute('SELECT COUNT(DISTINCT user_id) c FROM point_ledger').fetchone()['c']",
                "    await message.reply_text(",
                "        f'Stats\\nProducts={products} Orders={orders} Paid={paid} PointUsers={users}'",
                "    )",
            ]
        else:
            if method == "explicit_command":
                command_id = str(
                    getattr(getattr(cap, "trigger", None), "id", None)
                    or getattr(cap, "id", None)
                    or "command"
                )
                L.append(f"    _cmd = {command_id!r}")
                L.append("    if _cmd in {'about', 'info'}:")
                L.append("        await message.reply_text('بوت تيليجرام جاهز. استخدم /help لعرض الأوامر.')")
                L.append("    else:")
                L.append("        await message.reply_text(f'أمر /{_cmd} — جاهز.')")
            else:
                L.append("    from app.services import generic as generic_svc")
                L.append(
                    f"    result = generic_svc.act({svc!r}, {method!r}, user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
                L.append("    await message.reply_text(result)")
    return L



