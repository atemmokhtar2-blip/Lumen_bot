"""Emit handlers, keyboards, main.py registration for generated bots."""
from __future__ import annotations

from .coding_emit_foundation import _msg
from .registry import get_capability
from .schema import BotSpec, Feature
def _emit_keyboards(spec: BotSpec) -> str:
    """Build a launch-ready main menu (max ~10 rows) with cmd: callbacks."""
    lang = (spec.bot.language or "ar").lower()
    ar = lang.startswith("ar")

    if ar:
        curated = [
            ("🛍️ المتجر", "shopcatalog"),
            ("🛒 السلة", "cartview"),
            ("📦 طلباتي", "shopmyorders"),
            ("⭐ النقاط", "balance"),
            ("💎 الخطط", "plans"),
            ("👛 المحفظة", "walletbalance"),
            ("🎟️ كوبون", "couponapply"),
            ("🎫 تذكرة دعم", "ticketopen"),
            ("🏆 المتصدرين", "leaderboard"),
            ("🌐 اللغة", "lang"),
        ]
    else:
        curated = [
            ("🛍️ Shop", "shopcatalog"),
            ("🛒 Cart", "cartview"),
            ("📦 My orders", "shopmyorders"),
            ("⭐ Points", "balance"),
            ("💎 Plans", "plans"),
            ("👛 Wallet", "walletbalance"),
            ("🎟️ Coupon", "couponapply"),
            ("🎫 Support", "ticketopen"),
            ("🏆 Leaderboard", "leaderboard"),
            ("🌐 Language", "lang"),
        ]

    feat_keys = {f.feature for f in spec.features}
    commerce_ish = bool(
        feat_keys
        & {
            "shop_catalog", "shop_buy", "cart_view", "cart_checkout", "balance",
            "plans", "wallet_balance", "coupon_apply", "ticket_open",
        }
    ) or any(x in "".join(feat_keys) for x in ("shop", "cart", "wallet", "points"))

    rows: list[str] = []
    seen: set[str] = set()

    def _norm_cb(raw: str) -> str:
        raw = (raw or "").strip()
        if not raw:
            return ""
        if not any(raw.startswith(p) for p in ("cmd:", "nav:", "pay:", "act:")):
            raw = f"cmd:{raw}"
        # Telegram callback_data: normalize dots/spaces from legacy packs
        if raw.startswith("cmd:"):
            body = raw[4:].replace(".", "").replace(" ", "").replace("-", "_").lower()
            return f"cmd:{body}"
        return raw

    # Commerce / global launch: curated menu only (avoid mixed broken start_buttons)
    if commerce_ish:
        for label, cmd in curated:
            cb = f"cmd:{cmd}"
            rows.append(
                f"        [InlineKeyboardButton({label!r}, callback_data={cb!r})],"
            )
            seen.add(cb)
    else:
        for b in spec.start_buttons:
            cb = _norm_cb(b.callback_id or "")
            if not cb or cb in seen:
                continue
            rows.append(
                f"        [InlineKeyboardButton({b.label!r}, callback_data={cb!r})],"
            )
            seen.add(cb)
            if len(rows) >= 10:
                break
        if len(rows) < 4:
            for label, cmd in curated:
                cb = f"cmd:{cmd}"
                if cb in seen:
                    continue
                rows.append(
                    f"        [InlineKeyboardButton({label!r}, callback_data={cb!r})],"
                )
                seen.add(cb)
                if len(rows) >= 10:
                    break

    if len(rows) < 4:
        for feat in spec.features:
            if feat.trigger.type != "command":
                continue
            if feat.trigger.id in {"start", "help"}:
                continue
            cb = f"cmd:{feat.trigger.id}"
            if cb in seen:
                continue
            label = (feat.messages.prompt or feat.feature or feat.trigger.id).replace("_", " ")[:28]
            rows.append(
                f"        [InlineKeyboardButton({label!r}, callback_data={cb!r})],"
            )
            seen.add(cb)
            if len(rows) >= 8:
                break

    body = "\n".join(rows) if rows else "        # no buttons"
    return (
        '"""Inline keyboards derived from BotSpec."""\n'
        "from __future__ import annotations\n\n"
        "from telegram import InlineKeyboardButton, InlineKeyboardMarkup\n\n\n"
        "def main_keyboard() -> InlineKeyboardMarkup | None:\n"
        "    rows = [\n"
        f"{body}\n"
        "    ]\n"
        "    rows = [r for r in rows if r]\n"
        "    if not rows:\n"
        "        return None\n"
        "    return InlineKeyboardMarkup(rows)\n"
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
    if method in {"catalog", "list_content", "flash_list", "search", "product_info", "recommend"}:
        L.append("    await message.reply_text(market_svc.catalog())")
    elif method in {"add_item", "upload", "stock_set"}:
        L += [
            "    if not context.args:",
            "        await message.reply_text('Usage: /addproduct Title|price_cents  e.g. Book|999')",
            "        return",
            "    pid = market_svc.add_item(user.id, ' '.join(context.args))",
            "    await message.reply_text(f'Product added #{pid}')",
        ]
    elif method == "checkout" and svc == "cart":
        L.append("    await message.reply_text(market_svc.cart_checkout(user.id))")
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
    elif method in {"list_orders"}:
        L += [
            "    items = market_svc.list_orders()",
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
        L.append("    pct = market_svc.apply_coupon(context.args[0])")
        L.append("    await message.reply_text(f'Discount: {pct}%' if pct else 'Invalid coupon')")
    elif method in {"coupon_create", "create_coupon", "create_gift"}:
        need_args(2)
        L += [
            "    try:",
            "        code, pct = context.args[0], int(context.args[1])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    made = market_svc.create_coupon(code, pct)",
            f"    await message.reply_text(({ok!r} + ' ' + made) if made else {fail!r})",
        ]
    # ── cart ──────────────────────────────────────────────────────────
    elif method in {"add", "cart_add"} and svc in {"cart", "shop"}:
        L += [
            "    if not context.args:",
            "        await message.reply_text('Usage: /cartadd <product_id> [qty]' + chr(10) + market_svc.catalog())",
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
        L.append("    await message.reply_text(f'Wallet: {market_svc.wallet_balance(user.id)}')")
    elif method == "balance" or (method == "history" and svc == "points"):
        if method == "history":
            L.append("    bal = market_svc.points_balance(user.id)")
            L.append("    await message.reply_text(f'Points balance: {bal}')")
        else:
            L.append("    await message.reply_text(f'Points: {market_svc.points_balance(user.id)}')")
    elif method == "leaderboard":
        L += [
            "    rows = market_svc.leaderboard()",
            "    text = chr(10).join(f'{i+1}. {u}: {b}' for i, (u, b) in enumerate(rows)) if rows else 'لا يوجد متصدرون بعد — اكسب نقاط أولاً | No leaders yet'",
            "    await message.reply_text(text)",
        ]
    elif method in {"grant"} and svc == "points":
        need_args(2)
        L += [
            "    try:",
            "        uid, amt = int(context.args[0]), int(context.args[1])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    market_svc.points_credit(uid, amt, 'admin_grant')",
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
            "    # simple wallet move: add to target, subtract from sender if balance allows",
            "    if market_svc.wallet_balance(user.id) < amt:",
            "        await message.reply_text('Insufficient wallet balance — /topup <amount> first')",
            "        return",
            "    market_svc.wallet_add(user.id, -amt)",
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
            L.append("    ok_g = market_svc.grant_sub(target, plan_id)")
            L.append("    await message.reply_text((f'Subscription granted plan={plan_id}') if ok_g else 'Plan not found — try /plans')")
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
            "    try:",
            "        cid = int(context.args[0])",
            "    except ValueError:",
            f"        await message.reply_text({fail!r})",
            "        return",
            "    w = market_svc.draw_winner(cid)",
            "    await message.reply_text(f'Winner user_id={w}' if w else 'No entries')",
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
        L.append("    await message.reply_text(f'Wallet: {market_svc.wallet_balance(user.id)}')")
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
        L.append("    if context.args:")
        L.append("        lang = context.args[0].lower()[:2]")
        L.append("    else:")
        L.append("        cur = market_svc.get_lang(user.id) if hasattr(market_svc, 'get_lang') else 'en'")
        L.append("        lang = 'ar' if str(cur).startswith('en') else 'en'")
        L.append("    new_lang = market_svc.set_lang(user.id, lang)")
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
        L.append("    await message.reply_text(market_svc.coupon_create(user.id, ' '.join(context.args)))")
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
            "    await message.reply_text(market_svc.saas_add_member(tid, uid, role))",
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
    elif method in {"analytics_overview", "analytics_revenue", "dashboard", "stats"} and svc in {"analytics", "admin", "shop"}:
        L.append("    await message.reply_text(market_svc.analytics_dashboard())")
    elif method in {"audit_tail", "audit_log"}:
        L.append("    await message.reply_text(market_svc.audit_tail(20))")
    elif method in {"broadcast_segment"}:
        L.append("    rule = context.args[0] if context.args else 'all'")
        L.append("    await message.reply_text(market_svc.broadcast_segment_count(rule))")
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
    if lang.startswith("ar"):
        welcome = (
            f"مرحباً بك 👋\n"
            f"بوت متجر متكامل — {n_cmds} أمر جاهز.\n"
            "من القائمة بالأسفل: المتجر، السلة، الطلبات، النقاط، الخطط، المحفظة والدعم.\n"
            "اكتب /help لعرض كل الأوامر."
        )
    else:
        welcome = (
            f"Welcome 👋\n"
            f"Full commerce bot — {n_cmds} commands ready.\n"
            "Use the menu below: Shop, Cart, Orders, Points, Plans, Wallet & Support.\n"
            "Type /help for the full command list."
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
    need_market = any(
        _svc(f) in {
            'shop', 'payments', 'subscriptions', 'points', 'contests',
            'cart', 'growth', 'wallet', 'i18n', 'analytics', 'admin',
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

    # start / help always useful
    lines += [
        "async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
        "    message = update.effective_message",
        "    user = update.effective_user",
        "    if message is None:",
        "        return",
        f"    text = {welcome!r}",
        "    # Deep-link: /start ref_CODE or /start CODE → claim referral once",
        "    if user is not None and context.args:",
        "        raw = (context.args[0] or '').strip()",
        "        code = raw[4:] if raw.lower().startswith('ref_') else raw",
        "        if code:",
        "            try:",
        "                from app.services import market as market_svc",
        "                if market_svc.claim_referral(user.id, code):",
        "                    text = text + '\\nReferral applied.'",
        "            except Exception:",
        "                pass",
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

    # feature handlers
    for feat in spec.features:
        cap = get_capability(feat.feature)
        if cap is None:
            continue
        fname = f"handle_{feat.id}".replace("-", "_")
        ok = _msg(feat, "success", "تم بنجاح" if lang.startswith("ar") else "Done")
        fail = _msg(feat, "failure", "فشل التنفيذ" if lang.startswith("ar") else "Failed")

        if cap.method == "start":
            continue  # already have start_handler
        if cap.method == "help":
            continue

        lines.append(f"async def {fname}(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
        lines.append("    message = update.effective_message")
        lines.append("    user = update.effective_user")
        lines.append("    chat = update.effective_chat")
        lines.append("    if message is None or user is None:")
        lines.append("        return")

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
                lines.append("    await message.reply_text(content_svc.faq() if hasattr(content_svc, 'faq') else content_svc.rules())")
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
                lines.append("    context.user_data['awaiting'] = 'ticket_subject'")
                lines.append("    await message.reply_text('اكتب موضوع تذكرة الدعم')")
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
                lines.append("        parts.append(f'- {role}: {m[\'body\']}')")
                lines.append('    tail = "\\n".join(parts)')
                lines.append('    await message.reply_text(f"#{data[\'id\']} [{data[\'status\']}] {data[\'subject\']}\\n{tail}")')
            else:
                lines.append(f"    await message.reply_text({ok!r})")


        elif cap.service == "security":
            if cap.method == "checklist":
                lines.append("    await message.reply_text(security_svc.checklist())")
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
            else:
                lines.append(f"    await message.reply_text({ok!r})")


        elif cap.service in {
            "shop", "payments", "subscriptions", "points", "contests",
            "cart", "growth", "wallet", "i18n", "creator",
            "compliance", "analytics", "admin", "notify",
        }:
            lines.extend(_market_handler_lines(cap, ok, fail))
        else:
            # Durable generic executor — no empty success stubs
            lines.append("    from app.services import generic as generic_svc")
            lines.append(
                f"    result = generic_svc.act({cap.service!r}, {cap.method!r}, user.id, "
                "' '.join(context.args) if context.args else '')"
            )
            lines.append("    await message.reply_text(result)")
        lines.append("")
        lines.append("")

    # text router for multi-step captures
    if need_tasks or need_notes or need_welcome or need_tickets or need_security or need_market:
        lines += [
            "async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:",
            "    message = update.effective_message",
            "    user = update.effective_user",
            "    chat = update.effective_chat",
            "    if message is None or user is None or not message.text:",
            "        return",
            "    awaiting = context.user_data.get('awaiting')",
            "    if isinstance(awaiting, str) and awaiting.startswith('mkt_'):",
            "        text = (message.text or '').strip()",
            "        context.user_data.pop('awaiting', None)",
            "        from app.services import market as market_svc",
            "        key = awaiting[4:]",
            "        if key in ('coupon_apply', 'apply_coupon', 'redeem_gift'):",
            "            await message.reply_text(market_svc.coupon_apply_code(user.id, text, 0))",
            "            return",
            "        if key in ('wallet_topup', 'topup'):",
            "            try:",
            "                amt = int(text.replace(',', ' ').split()[0])",
            "                bal = market_svc.wallet_topup(user.id, amt)",
            "                await message.reply_text('تم الشحن. الرصيد: ' + str(bal))",
            "            except Exception:",
            "                await message.reply_text('أرسل رقماً صحيحاً / Send a valid number')",
            "            return",
            "        if 'transfer' in key:",
            "            parts = text.split()",
            "            if len(parts) < 2:",
            "                await message.reply_text('الصيغة: user_id amount')",
            "                return",
            "            try:",
            "                to_uid, amt = int(parts[0]), int(parts[1])",
            "                if market_svc.wallet_balance(user.id) < amt:",
            "                    await message.reply_text('رصيد غير كافٍ')",
            "                    return",
            "                market_svc.wallet_add(user.id, -amt)",
            "                bal = market_svc.wallet_add(to_uid, amt)",
            "                await message.reply_text('تم التحويل. رصيد المستلم: ' + str(bal))",
            "            except Exception:",
            "                await message.reply_text('صيغة غير صحيحة')",
            "            return",
            "        await message.reply_text('تم: ' + text[:100])",
            "        return",
            "    if awaiting == 'task_title':",
            "        tasks_svc.add_task(user.id, message.text.strip())",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text('تمت إضافة المهمة')",
            "        return",
            "    if awaiting == 'note_body':",
            "        notes_svc.add_note(user.id, message.text.strip())",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text('تمت إضافة الملاحظة')",
            "        return",
            "    if awaiting == 'welcome_message' and chat is not None:",
            "        welcome_svc.set_message(chat.id, message.text.strip())",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text('تم حفظ رسالة الترحيب')",
            "        return",
            "    if awaiting == 'ticket_subject':",
            "        tid = tickets_svc.open_ticket(user.id, message.text.strip(), chat.id if chat else 0)",
            "        context.user_data.pop('awaiting', None)",
            "        await message.reply_text(f'تم فتح التذكرة #{tid}')",
            "        return",
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

    lines.append("async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
    lines.append("    query = update.callback_query")
    lines.append("    if query is None:")
    lines.append("        return")
    lines.append("    await query.answer()")
    lines.append("    data = query.data or ''")
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
    lines.append("        }")
    lines.append("        _ALIASES = {")
    lines.append("            'shop': 'shopcatalog', 'catalog': 'shopcatalog', 'cart': 'cartview',")
    lines.append("            'orders': 'shopmyorders', 'myorders': 'shopmyorders', 'points': 'balance',")
    lines.append("            'wallet': 'walletbalance', 'support': 'ticketopen', 'ticket': 'ticketopen',")
    lines.append("            'coupon': 'couponapply', 'language': 'lang', 'buy': 'shopbuy',")
    lines.append("            'plans': 'plans', 'sub': 'plans', 'subs': 'plans', 'leaderboard': 'leaderboard',")
    lines.append("        }")
    lines.append("        fn = _CMD_MAP.get(cmd) or _CMD_MAP.get(cmd_compact)")
    lines.append("        if fn is None:")
    lines.append("            target = _ALIASES.get(cmd) or _ALIASES.get(cmd_compact)")
    lines.append("            if target:")
    lines.append("                fn = _CMD_MAP.get(target) or _CMD_MAP.get(target.replace('_', ''))")
    lines.append("        if fn is not None:")
    lines.append("            await fn(update, context)")
    lines.append("            return")
    lines.append("        message = update.effective_message")
    lines.append("        if message is not None:")
    lines.append("            await message.reply_text('Command /' + (data[4:] or '') + ' is not available.')")
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
        f.feature: f"handle_{f.id}".replace("-", "_") for f in spec.features if f.feature not in ("start", "help")
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
    imports_handlers = "start_handler, help_handler, callback_router"
    extra_imports = []
    for feat in spec.features:
        if feat.feature in ("start", "help"):
            continue
        extra_imports.append(f"handle_{feat.id}".replace("-", "_"))
    if extra_imports:
        imports_handlers += ", " + ", ".join(dict.fromkeys(extra_imports))
    need_market = any(
        (get_capability(f.feature) and get_capability(f.feature).service in {
            "shop", "payments", "subscriptions", "points", "contests",
            "cart", "growth", "wallet", "i18n", "analytics", "admin",
        })  # type: ignore
        for f in spec.features
    )
    if need_tasks or need_notes or need_welcome or need_tickets or need_security or need_market:
        imports_handlers += ", text_router"
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
    if need_tasks or need_notes or need_welcome or need_tickets or need_security or need_market:
        text_handler = "\n    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))"
    if need_welcome:
        text_handler += "\n    app.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.CHAT_MEMBER))"

    pay_handler = ""
    if need_pay:
        pay_handler = (
            "\n    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))"
            "\n    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))"
        )

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


async def _post_init(app: Application) -> None:
    # Telegram allows at most 100 bot commands in the menu.
    try:
        await app.bot.set_my_commands([
            {bot_cmds}
        ])
    except Exception as exc:
        logger.warning("set_my_commands skipped: %s", exc)


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env")
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .build()
    )
{reg_text}
    app.add_handler(CallbackQueryHandler(callback_router)){text_handler}{pay_handler}
    return app


def main() -> None:
    logger.info("starting bot")
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


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



