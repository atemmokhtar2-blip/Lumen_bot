"""Emit handlers, keyboards, main.py registration for generated bots."""
from __future__ import annotations

from .coding_emit_foundation import _msg
from .registry import get_capability
from .schema import BotSpec, Feature
def _emit_keyboards(spec: BotSpec) -> str:
    """Main menu from ACTUAL spec.features only — never invent cart/points/etc."""
    lang = (spec.bot.language or "ar").lower()
    ar = lang.startswith("ar")

    feat_btn = {
        "shop_catalog": ("🛍️ المنتجات", "🛍️ Products", "shopcatalog"),
        "product_info": ("ℹ️ تفاصيل منتج", "ℹ️ Product info", "productinfo"),
        "product_search": ("🔎 بحث", "🔎 Search", "productsearch"),
        "order_track": ("📦 متابعة الطلب", "📦 Track order", "ordertrack"),
        "shop_my_orders": ("📋 طلباتي", "📋 My orders", "shopmyorders"),
        "pay_methods": ("💳 طرق الدفع", "💳 Payments", "pay"),
        "shipping_set": ("🚚 الشحن والتوصيل", "🚚 Shipping", "shippingset"),
        "ticket_open": ("📞 الدعم", "📞 Support", "ticket"),
        "ticket_my": ("🎫 تذاكري", "🎫 My tickets", "mytickets"),
        "faq_list": ("❓ الأسئلة الشائعة", "❓ FAQ", "faqlist"),
        "faq_show": ("❓ FAQ", "❓ FAQ", "faq"),
        "cart_view": ("🛒 السلة", "🛒 Cart", "cartview"),
        "wallet_balance": ("👛 المحفظة", "👛 Wallet", "walletbalance"),
        "coupon_apply": ("🎟️ كوبون", "🎟️ Coupon", "couponapply"),
        "points_balance": ("⭐ النقاط", "⭐ Points", "balance"),
        "plans": ("💎 الخطط", "💎 Plans", "plans"),
        "lang": ("🌐 اللغة", "🌐 Language", "lang"),
    }

    ordered_keys: list[str] = []
    seen: set[str] = set()
    for f in spec.features:
        if f.feature in seen or f.feature in {"start", "help"}:
            continue
        seen.add(f.feature)
        ordered_keys.append(f.feature)

    rows: list[str] = []
    seen_cb: set[str] = set()
    for k in ordered_keys:
        if k in feat_btn:
            ar_l, en_l, body_cb = feat_btn[k]
            label = ar_l if ar else en_l
            cb = f"cmd:{body_cb}"
        else:
            ff = next((x for x in spec.features if x.feature == k), None)
            if not ff or ff.trigger.type != "command" or ff.trigger.id in {"start", "help"}:
                continue
            label = (ff.messages.prompt or k).replace("_", " ")[:28]
            body_cb = ff.trigger.id.replace(".", "").replace("-", "_").lower()
            cb = f"cmd:{body_cb}"
        if cb in seen_cb:
            continue
        rows.append(
            f"        [InlineKeyboardButton({label!r}, callback_data={cb!r})],"
        )
        seen_cb.add(cb)
        if len(rows) >= 10:
            break

    body = "\n".join(rows) if rows else "        # no buttons"
    # NOTE: body above is wrong - we need real newlines in the *output* source
    body = chr(10).join(rows) if rows else "        # no buttons"
    return (
        '"""Inline keyboards derived from BotSpec features only."""'
        + chr(10)
        + "from __future__ import annotations"
        + chr(10)
        + chr(10)
        + "from telegram import InlineKeyboardButton, InlineKeyboardMarkup"
        + chr(10)
        + chr(10)
        + chr(10)
        + "def main_keyboard() -> InlineKeyboardMarkup | None:"
        + chr(10)
        + "    rows = ["
        + chr(10)
        + f"{body}"
        + chr(10)
        + "    ]"
        + chr(10)
        + "    rows = [r for r in rows if r]"
        + chr(10)
        + "    if not rows:"
        + chr(10)
        + "        return None"
        + chr(10)
        + "    return InlineKeyboardMarkup(rows)"
        + chr(10)
    )


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



def _emit_handlers(spec: BotSpec) -> str:
    lang = (spec.bot.language or "ar").lower()
    n_cmds = len([f for f in spec.features if f.trigger.type == "command"])
    bot_name = (getattr(spec.bot, "name", None) or "Bot").strip() or "Bot"
    if lang.startswith("ar"):
        welcome = (
            f"مرحباً بك في {bot_name} 👋\n"
            f"الأوامر المتاحة: {n_cmds}.\n"
            "اضغط الأزرار أو اكتب /help."
        )
    else:
        welcome = (
            f"Welcome to {bot_name} 👋\n"
            f"{n_cmds} commands available.\n"
            "Use the menu or /help."
        )

    help_lines = []
    help_lines.append(
        f"قائمة الأوامر ({n_cmds}):" if lang.startswith("ar") else f"Commands ({n_cmds}):"
    )
    for feat in spec.features:
        if feat.trigger.type == "command":
            desc = feat.messages.prompt or feat.feature
            help_lines.append(f"/{feat.trigger.id} — {desc}")
    help_text = "\n".join(help_lines) if help_lines else "/start"

    # collect needs
    def _svc(f):
        c = get_capability(f.feature)
        return c.service if c else ""

    need_mod = any(_svc(f) == "moderation" for f in spec.features)
    need_tasks = any(_svc(f) == "tasks" for f in spec.features)
    need_notes = any(_svc(f) == "notes" for f in spec.features)
    need_content = any(_svc(f) == "content" for f in spec.features)
    need_welcome = any(_svc(f) == "welcome" for f in spec.features)
    need_tickets = any(_svc(f) == "tickets" for f in spec.features)
    need_security = any(_svc(f) == "security" for f in spec.features)
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
    _extra_set = {"shop", "booking", "crm", "reminders", "community", "edu", "hr", "utils", "gate"}
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
    if need_content:
        imports.append("from app.services import content as content_svc")
    if need_welcome:
        imports.append("from app.services import welcome as welcome_svc")
    if need_tickets:
        imports.append("from app.services import tickets as tickets_svc")
    if need_security:
        imports.append("from app.services import security as security_svc")
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
            if cap.method in {"pin_message", "delete_message"}:
                lines.append("    if chat is None or message.reply_to_message is None:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        mid = message.reply_to_message.message_id")
                if cap.method == "pin_message":
                    lines.append("        await moderation_svc.pin_message(context, chat.id, mid)")
                else:
                    lines.append("        await moderation_svc.delete_message(context, chat.id, mid)")
                lines.append(f"        await message.reply_text({ok!r})")
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
                    lines.append("        await message.reply_text(f'user_id={target_id}')" )
                    lines.append("        return")
                m = method_map.get(cap.method, "warn_user")
                lines.append(f"        await moderation_svc.{m}(context, chat.id, target_id)")
                lines.append(f"        await message.reply_text({ok!r})")
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
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    if tasks_svc.done_task(user.id, tid):")
                lines.append(f"        await message.reply_text({ok!r})")
                lines.append("    else:")
                lines.append(f"        await message.reply_text({fail!r})")
            elif cap.method == "delete_task":
                lines.append("    if not context.args:")
                lines.append(f"        await message.reply_text({fail!r})")
                lines.append("        return")
                lines.append("    try:")
                lines.append("        tid = int(context.args[0])")
                lines.append("    except ValueError:")
                lines.append(f"        await message.reply_text({fail!r})")
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
        elif cap.service in {"translate", "ocr", "scheduler"} or (
            cap.service in {"utils", "content", "generic", "reminders"}
            and cap.method in {
                "translate", "translate_toggle", "ocr_image", "ocr_hint",
                "schedule_note", "job_list", "job_cancel",
                "voice_intake", "payment_info", "faq",
            }
        ):
            # Phase 8/14 scaffolds via generic service specialists
            lines.append("    from app.services import generic as generic_svc")
            if cap.method in {"voice_intake", "voice"}:
                lines.append(
                    "    result = generic_svc.voice_intake(user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
            elif cap.method in {"payment_info", "pay_info"}:
                lines.append(
                    "    result = generic_svc.payment_info(user.id, "
                    "' '.join(context.args) if context.args else '')"
                )
            elif cap.method in {"faq", "faq_list", "faq_search"}:
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
    if need_tasks or need_notes or need_welcome or need_tickets or need_security or need_market or need_ocr or need_voice:
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
                    "            await message.reply_text(market_svc.coupon_apply_code(user.id, text, 0))",
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
            "async def photo_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            *(
                [
                    "    try:",
                    "        from app.flow_engine import handle_photo as _flow_photo",
                    "        if await _flow_photo(update, context):",
                    "            return",
                    "    except Exception as _photo_flow_exc:",
                    "        import logging as _logging",
                    "        _logging.getLogger(__name__).debug('flow photo: %s', _photo_flow_exc)",
                ]
                if (need_market or need_tickets or need_ocr)
                else []
            ),
            "    # Phase 9: OCR path when user sends a photo (or after /ocr awaiting)",
            "    if message is not None and user is not None and message.photo:",
            "        awaiting = context.user_data.get('awaiting')",
            "        try:",
            "            from app.services import generic as generic_svc",
            "            caption = (message.caption or '').strip()",
            "            photo = message.photo[-1]",
            "            path = ''",
            "            try:",
            "                tg_file = await context.bot.get_file(photo.file_id)",
            "                path = f'/tmp/ocr_{user.id}_{photo.file_id}.jpg'",
            "                await tg_file.download_to_drive(path)",
            "            except Exception:",
            "                path = ''",
            "            if path and hasattr(generic_svc, 'ocr_from_image'):",
            "                result = generic_svc.ocr_from_image(user.id, path, caption)",
            "            else:",
            "                result = generic_svc.ocr_hint(user.id, caption or 'photo_received')",
            "            if awaiting == 'ocr_photo':",
            "                context.user_data.pop('awaiting', None)",
            "            await message.reply_text(result)",
            "        except Exception:",
            "            await message.reply_text('تم استلام الصورة. استخدم /ocr أو فعّل pytesseract.')",
            "",
            "",
        ]
        if need_voice:
            lines += [
            "async def voice_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    if message is None or user is None:",
            "        return",
            "    try:",
            "        from app.services import generic as generic_svc",
            "        voice = message.voice or message.audio",
            "        if voice is None:",
            "            return",
            "        path = ''",
            "        try:",
            "            tg_file = await context.bot.get_file(voice.file_id)",
            "            ext = 'ogg' if message.voice else 'mp3'",
            "            path = f'/tmp/voice_{user.id}_{voice.file_id[:24]}.{ext}'",
            "            await tg_file.download_to_drive(path)",
            "        except Exception:",
            "            path = ''",
            "        duration = int(getattr(voice, 'duration', 0) or 0)",
            "        if hasattr(generic_svc, 'voice_from_file'):",
            "            result = generic_svc.voice_from_file(user.id, path, voice.file_id, duration)",
            "        else:",
            "            result = generic_svc.voice_intake(user.id, f'file:{voice.file_id}')",
            "        await message.reply_text(result)",
            "    except Exception:",
            "        await message.reply_text('تم استلام الصوت. استخدم /voice أو أعد المحاولة.')",
            "",
            "",
            ]
        lines += [
            "async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    try:",
            "        from app.flow_engine import clear_flow",
            "        clear_flow(context)",
            "    except Exception:",
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
            label = (feat.feature or feat.trigger.id or "action").replace("_", " ")
            lines.append(f"        await message.reply_text({label!r})")
        lines.append("")

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
    if need_market or need_tickets or need_tasks or need_notes:
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
            h = f"handle_{feat.id}".replace("-", "_")
            handler_regs.append(f'    app.add_handler(CommandHandler({cmd!r}, {h}))')
            commands.append((cmd, feat.feature))

    # ensure start/help registered
    reg_text = "\n".join(dict.fromkeys(handler_regs))
    if 'CommandHandler("start"' not in reg_text:
        reg_text = '    app.add_handler(CommandHandler("start", start_handler))\n' + reg_text
    if 'CommandHandler("help"' not in reg_text:
        reg_text += '\n    app.add_handler(CommandHandler("help", help_handler))'

    # Friendly aliases so /cart works even if trigger is cartview, etc.
    _alias_map = {
        "shop": "handle_shop_catalog",
        "catalog": "handle_shop_catalog",
        "cart": "handle_cart_view",
        "orders": "handle_shop_orders",
        "points": "handle_balance",
        "sub": "handle_plans",
        "subs": "handle_plans",
        "invite": "handle_referral_invite",
        "checkin": "handle_daily_checkin",
        "wallet": "handle_wallet_balance",
    }
    # Only add alias if target handler function exists in imports later — filter by features
    feat_names = {f.feature for f in spec.features}
    feat_to_handler = {
        f.feature: f"handle_{f.id}".replace("-", "_")
        for f in spec.features
        if f.feature not in ("start", "help") and f.trigger.type == "command"
    }
    # map alias to feature
    alias_feature = {
        "shop": "shop_catalog",
        "catalog": "shop_catalog",
        "cart": "cart_view",
        "orders": "shop_orders",
        "points": "balance",
        "sub": "plans",
        "subs": "plans",
        "invite": "referral_invite",
        "checkin": "daily_checkin",
        "wallet": "wallet_balance",
    }
    for alias, feat in alias_feature.items():
        if feat in feat_to_handler:
            h = feat_to_handler[feat]
            # avoid duplicate if alias already the trigger id
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
        fname = f"handle_{feat.id}".replace("-", "_")
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
    if need_tasks or need_notes or need_welcome or need_tickets or need_security or need_market or need_ocr or need_voice:
        imports_handlers += ", text_router, photo_router, cancel_handler"
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
    for c, d in commands:
        c2 = "".join(ch for ch in (c or "").lower().replace("-", "_") if ch.isalnum() or ch == "_")[:32]
        if not c2 or c2 in seen_c or not c2[0].isalpha():
            continue
        seen_c.add(c2)
        desc = (d or c2).replace("_", " ").strip()[:48] or c2
        uniq_cmds.append((c2, desc))
    uniq_cmds.sort(key=lambda x: (_prio.get(x[0], 50), x[0]))
    menu_cmds = uniq_cmds[:100]
    bot_cmds = ",\n        ".join(
        f"BotCommand({c!r}, {d!r})" for c, d in menu_cmds
    ) or 'BotCommand("start", "start")'

    text_handler = ""
    if need_tasks or need_notes or need_welcome or need_tickets or need_security or need_market or need_ocr or need_voice:
        text_handler = (
            "\n    app.add_handler(CommandHandler('cancel', cancel_handler))"
            "\n    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))"
            "\n    app.add_handler(MessageHandler(filters.PHOTO, photo_router))"
        )
    else:
        text_handler = ""
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
        from app.services import generic as generic_svc
        batch = int((_os.getenv("SCHEDULE_BATCH_LIMIT") or "20").strip() or "20")
        due = generic_svc.list_due_reminders(limit=max(1, min(batch, 50)))
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
                    generic_svc.mark_reminder_fired(int(iid))
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
    return app


def main() -> None:
    logger.info("starting bot name=%s", {spec.bot.name!r})
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
'''


def _emit_requirements() -> str:
    return (
        "python-telegram-bot>=22.8,<23\n"
        "python-dotenv>=1.2.2\n"
    )


def _emit_env() -> str:
    return (
        "TELEGRAM_BOT_TOKEN=\n"
        "PAYMENT_PROVIDER_TOKEN=\n"
        "ADMIN_USER_IDS=\n"
        "DEFAULT_CURRENCY=USD\n"
    )



def _emit_readme(spec: BotSpec) -> str:
    return f"""# {spec.bot.name}

Generated by **spec_core** (zero-AI deterministic engine).

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# put TELEGRAM_BOT_TOKEN in .env
python main.py
```

## Features

{chr(10).join(f"- `{f.feature}` via {f.trigger.type}:{f.trigger.id}" for f in spec.features)}
"""



