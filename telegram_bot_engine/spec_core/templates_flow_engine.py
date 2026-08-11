"""Flow Engine — multi-step wizards for generated Telegram bots (zero-AI).

Copied into projects as app/flow_engine.py.
Supports: validation, back/cancel/skip, choices, photos, confirm, timeout,
and optional Vodafone Cash style manual payment verification (reference + admin).
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

# ── Flow definitions (declarative) ──────────────────────────────────────────

FLOW_TIMEOUT_SEC = 15 * 60  # 15 minutes idle

FLOWS: dict[str, dict[str, Any]] = {
    "add_product": {
        "title": "إضافة منتج",
        "steps": [
            {
                "id": "title",
                "prompt": "📦 ما اسم المنتج؟ (3–100 حرف)\n/cancel إلغاء · /back رجوع",
                "type": "text",
                "min_len": 3,
                "max_len": 100,
            },
            {
                "id": "price",
                "prompt": "💰 ما السعر؟ (رقم، مثال: 1200 أو 12.50)\n/cancel · /back · /skip = 0",
                "type": "money",
                "min": 0,
                "optional": False,
            },
            {
                "id": "category",
                "prompt": "📂 اختر الفئة:",
                "type": "choice",
                "choices": [
                    ("electronics", "إلكترونيات"),
                    ("clothes", "ملابس"),
                    ("food", "طعام"),
                    ("other", "أخرى"),
                ],
            },
            {
                "id": "description",
                "prompt": "📝 اكتب وصف المنتج (اختياري)\n/skip للتخطي · /back · /cancel",
                "type": "text",
                "max_len": 500,
                "optional": True,
            },
            {
                "id": "photo",
                "prompt": "📸 أرسل صورة المنتج (اختياري)\n/skip للتخطي · /back · /cancel",
                "type": "photo",
                "optional": True,
            },
            {
                "id": "confirm",
                "prompt": "✅ تأكيد إضافة المنتج:",
                "type": "confirm",
            },
        ],
        "on_complete": "add_product",
    },
    "open_ticket": {
        "title": "فتح تذكرة دعم",
        "steps": [
            {
                "id": "subject",
                "prompt": "🎫 موضوع التذكرة؟ (5–120 حرف)\n/cancel · /back",
                "type": "text",
                "min_len": 5,
                "max_len": 120,
            },
            {
                "id": "body",
                "prompt": "📝 تفاصيل المشكلة:\n/cancel · /back",
                "type": "text",
                "min_len": 5,
                "max_len": 2000,
            },
            {
                "id": "priority",
                "prompt": "⚡ الأولوية:",
                "type": "choice",
                "choices": [
                    ("low", "منخفضة"),
                    ("normal", "عادية"),
                    ("high", "عالية"),
                ],
            },
            {"id": "confirm", "prompt": "✅ تأكيد فتح التذكرة:", "type": "confirm"},
        ],
        "on_complete": "open_ticket",
    },
    "wallet_topup": {
        "title": "شحن محفظة",
        "steps": [
            {
                "id": "amount",
                "prompt": "💵 مبلغ الشحن؟ (رقم صحيح)\n/cancel · /back",
                "type": "number",
                "min": 1,
                "max": 1_000_000,
            },
            {"id": "confirm", "prompt": "✅ تأكيد الشحن:", "type": "confirm"},
        ],
        "on_complete": "wallet_topup",
    },
    "vodafone_cash": {
        "title": "دفع فودافون كاش",
        "steps": [
            {
                "id": "amount",
                "prompt": (
                    "📱 دفع فودافون كاش\n"
                    "أدخل المبلغ المحوَّل (رقم):\n"
                    "/cancel · /back"
                ),
                "type": "money",
                "min": 1,
            },
            {
                "id": "reference",
                "prompt": (
                    "🔢 أرسل رقم العملية / مرجع التحويل من رسالة فودافون\n"
                    "(مثال: 123456789012)\n"
                    "/cancel · /back"
                ),
                "type": "text",
                "min_len": 6,
                "max_len": 40,
                "pattern": r"^[A-Za-z0-9\-]{6,40}$",
            },
            {
                "id": "screenshot",
                "prompt": "📸 أرسل لقطة شاشة التحويل (اختياري)\n/skip · /back · /cancel",
                "type": "photo",
                "optional": True,
            },
            {
                "id": "confirm",
                "prompt": "✅ تأكيد إرسال إثبات الدفع للمراجعة:",
                "type": "confirm",
            },
        ],
        "on_complete": "vodafone_cash",
    },

    "pay_methods": {
        "title": "اختيار طريقة الدفع",
        "steps": [
            {
                "id": "method",
                "prompt": "💳 اختر طريقة الدفع:",
                "type": "choice",
                "choices": [
                    ("telegram", "Telegram Payments"),
                    ("vodafone", "فودافون كاش"),
                    ("wallet", "رصيد المحفظة"),
                ],
            },
            {
                "id": "confirm",
                "prompt": "✅ تأكيد طريقة الدفع:",
                "type": "confirm",
            },
        ],
        "on_complete": "pay_methods",
    },
    "coupon": {
        "title": "تطبيق كوبون",
        "steps": [
            {
                "id": "code",
                "prompt": "🏷️ أرسل كود الكوبون:\n/cancel",
                "type": "text",
                "min_len": 3,
                "max_len": 40,
            },
        ],
        "on_complete": "coupon",
    },
}


def _state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    st = context.user_data.get("flow")
    if not isinstance(st, dict):
        st = {}
        context.user_data["flow"] = st
    return st


def clear_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("flow", None)
    context.user_data.pop("awaiting", None)


def active_flow(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    st = context.user_data.get("flow")
    if not isinstance(st, dict):
        return None
    # timeout
    started = float(st.get("ts") or 0)
    if started and (time.time() - started) > FLOW_TIMEOUT_SEC:
        clear_flow(context)
        return None
    return st.get("name")


async def start_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    name: str,
    *,
    preset: dict[str, Any] | None = None,
) -> None:
    if name not in FLOWS:
        msg = update.effective_message
        if msg:
            await msg.reply_text("هذا المسار غير متاح.")
        return
    context.user_data["flow"] = {
        "name": name,
        "step": 0,
        "data": dict(preset or {}),
        "ts": time.time(),
    }
    context.user_data.pop("awaiting", None)
    await _prompt_current(update, context)


def _current_step(st: dict[str, Any]) -> dict[str, Any] | None:
    flow = FLOWS.get(st.get("name") or "")
    if not flow:
        return None
    steps = flow.get("steps") or []
    idx = int(st.get("step") or 0)
    if idx < 0 or idx >= len(steps):
        return None
    return steps[idx]


async def _prompt_current(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = _state(context)
    st["ts"] = time.time()
    step = _current_step(st)
    msg = update.effective_message
    if not step or msg is None:
        return
    kind = step.get("type")
    prompt = str(step.get("prompt") or "")
    if kind == "choice":
        rows = []
        row: list[InlineKeyboardButton] = []
        for cid, label in step.get("choices") or []:
            row.append(
                InlineKeyboardButton(
                    label, callback_data=f"flow:choice:{cid}"[:64]
                )
            )
            if len(row) >= 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append(
            [
                InlineKeyboardButton("⬅️ رجوع", callback_data="flow:back"),
                InlineKeyboardButton("❌ إلغاء", callback_data="flow:cancel"),
            ]
        )
        await msg.reply_text(prompt, reply_markup=InlineKeyboardMarkup(rows))
        return
    if kind == "confirm":
        data = st.get("data") or {}
        summary = _format_summary(st.get("name") or "", data)
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ تأكيد", callback_data="flow:yes"),
                    InlineKeyboardButton("❌ إلغاء", callback_data="flow:cancel"),
                ],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="flow:back")],
            ]
        )
        await msg.reply_text(f"{prompt}\n\n{summary}", reply_markup=kb)
        return
    await msg.reply_text(prompt)


def _format_summary(name: str, data: dict[str, Any]) -> str:
    lines = []
    for k, v in data.items():
        if k.startswith("_"):
            continue
        if k == "photo_file_id":
            lines.append(f"• صورة: مرفقة")
            continue
        lines.append(f"• {k}: {v}")
    return "\n".join(lines) or "(لا بيانات)"


def _validate(step: dict[str, Any], text: str) -> tuple[bool, Any, str]:
    kind = step.get("type")
    optional = bool(step.get("optional"))
    raw = (text or "").strip()
    if not raw and optional:
        return True, None, ""
    if kind == "text":
        if len(raw) < int(step.get("min_len") or 0):
            return False, None, f"النص قصير جداً (الحد الأدنى {step.get('min_len')})"
        if len(raw) > int(step.get("max_len") or 5000):
            return False, None, "النص طويل جداً"
        pat = step.get("pattern")
        if pat and not re.match(pat, raw):
            return False, None, "الصيغة غير صحيحة"
        return True, raw, ""
    if kind == "number":
        try:
            n = int(re.sub(r"[^\d\-]", "", raw) or "x")
        except Exception:
            return False, None, "أرسل رقماً صحيحاً"
        if n < int(step.get("min") or 0):
            return False, None, f"الحد الأدنى {step.get('min')}"
        if step.get("max") is not None and n > int(step["max"]):
            return False, None, f"الحد الأقصى {step.get('max')}"
        return True, n, ""
    if kind == "money":
        cleaned = raw.replace(",", ".").strip()
        m = re.search(r"(\d+(?:\.\d{1,2})?)", cleaned)
        if not m:
            return False, None, "أرسل مبلغاً رقمياً مثل 100 أو 12.50"
        val = float(m.group(1))
        if val < float(step.get("min") or 0):
            return False, None, f"الحد الأدنى {step.get('min')}"
        # store as cents integer
        cents = int(round(val * 100))
        return True, cents, ""
    return True, raw, ""


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if the message was consumed by an active flow."""
    st = context.user_data.get("flow")
    if not isinstance(st, dict) or not st.get("name"):
        return False
    if active_flow(context) is None:
        msg = update.effective_message
        if msg:
            await msg.reply_text("انتهت مهلة العملية. ابدأ من جديد.")
        return True
    text = (update.effective_message.text or "").strip() if update.effective_message else ""
    low = text.lower()

    if low in {"/cancel", "cancel", "إلغاء"}:
        clear_flow(context)
        if update.effective_message:
            await update.effective_message.reply_text("تم إلغاء العملية.")
        return True
    if low in {"/back", "back", "رجوع"}:
        st["step"] = max(0, int(st.get("step") or 0) - 1)
        # drop last field if possible
        step = _current_step(st)
        if step and step.get("id") in (st.get("data") or {}):
            st["data"].pop(step["id"], None)
        await _prompt_current(update, context)
        return True
    if low in {"/skip", "skip", "تخطي"}:
        step = _current_step(st)
        if step and step.get("optional"):
            st["data"][step["id"]] = None
            st["step"] = int(st.get("step") or 0) + 1
            if _current_step(st) is None:
                await _finish(update, context)
            else:
                await _prompt_current(update, context)
            return True
        if update.effective_message:
            await update.effective_message.reply_text("هذه الخطوة مطلوبة — لا يمكن تخطيها.")
        return True

    step = _current_step(st)
    if not step:
        await _finish(update, context)
        return True
    if step.get("type") in {"choice", "confirm", "photo"}:
        if update.effective_message:
            await update.effective_message.reply_text(
                "استخدم الأزرار أو أرسل النوع المطلوب (صورة/اختيار)."
            )
        return True

    ok, value, err = _validate(step, text)
    if not ok:
        if update.effective_message:
            await update.effective_message.reply_text(f"❌ {err}\nأعد المحاولة:")
        return True
    st["data"][step["id"]] = value
    st["step"] = int(st.get("step") or 0) + 1
    st["ts"] = time.time()
    if _current_step(st) is None:
        await _finish(update, context)
    else:
        await _prompt_current(update, context)
    return True


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    st = context.user_data.get("flow")
    if not isinstance(st, dict) or not st.get("name"):
        return False
    if active_flow(context) is None:
        return False
    step = _current_step(st)
    if not step or step.get("type") != "photo":
        return False
    msg = update.effective_message
    if msg is None or not msg.photo:
        return False
    file_id = msg.photo[-1].file_id
    st["data"]["photo_file_id"] = file_id
    st["data"][step["id"]] = file_id
    st["step"] = int(st.get("step") or 0) + 1
    st["ts"] = time.time()
    if _current_step(st) is None:
        await _finish(update, context)
    else:
        await _prompt_current(update, context)
    return True


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    q = update.callback_query
    if q is None or not q.data or not str(q.data).startswith("flow:"):
        return False
    await q.answer()
    st = context.user_data.get("flow")
    if not isinstance(st, dict) or not st.get("name"):
        await q.edit_message_text("لا توجد عملية جارية.")
        return True
    if active_flow(context) is None:
        clear_flow(context)
        await q.edit_message_text("انتهت مهلة العملية.")
        return True

    action = str(q.data)[5:]  # after flow:
    if action == "cancel":
        clear_flow(context)
        await q.edit_message_text("تم إلغاء العملية.")
        return True
    if action == "back":
        st["step"] = max(0, int(st.get("step") or 0) - 1)
        # fake message for prompt
        class _U:
            effective_message = q.message
        await _prompt_current(_U(), context)  # type: ignore
        return True
    if action == "yes":
        st["step"] = int(st.get("step") or 0) + 1
        class _U:
            effective_message = q.message
            effective_user = q.from_user
            effective_chat = q.message.chat if q.message else None
        await _finish(_U(), context)  # type: ignore
        return True
    if action.startswith("choice:"):
        cid = action.split(":", 1)[1]
        step = _current_step(st)
        if step and step.get("type") == "choice":
            label = cid
            for c, lab in step.get("choices") or []:
                if c == cid:
                    label = lab
                    break
            st["data"][step["id"]] = label
            st["step"] = int(st.get("step") or 0) + 1
            class _U:
                effective_message = q.message
                effective_user = q.from_user
            if _current_step(st) is None:
                await _finish(_U(), context)  # type: ignore
            else:
                await _prompt_current(_U(), context)  # type: ignore
        return True
    return True


async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    st = _state(context)
    name = st.get("name") or ""
    data = dict(st.get("data") or {})
    clear_flow(context)
    user = update.effective_user
    msg = update.effective_message
    uid = int(user.id) if user else 0
    try:
        result = await _execute(name, uid, data, update, context)
    except Exception as e:
        result = f"فشل التنفيذ: {type(e).__name__}"
    if msg:
        await msg.reply_text(result)


async def _execute(
    name: str,
    user_id: int,
    data: dict[str, Any],
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> str:
    if name == "add_product":
        from app.services import market as market_svc

        title = str(data.get("title") or "Item")
        price_cents = int(data.get("price") or 0)
        category = str(data.get("category") or "other")
        desc = data.get("description") or ""
        photo = data.get("photo_file_id") or data.get("photo")
        if hasattr(market_svc, "add_item_structured"):
            pid = market_svc.add_item_structured(
                user_id,
                title=title,
                price_cents=price_cents,
                category=category,
                description=str(desc or ""),
                photo_file_id=str(photo or ""),
            )
        else:
            pid = market_svc.add_item(user_id, f"{title}|{price_cents}")
        return f"✅ تم إضافة المنتج #{pid}\n{title} — {price_cents/100:.2f}"

    if name == "open_ticket":
        from app.services import tickets as tickets_svc

        chat = update.effective_chat
        subject = str(data.get("subject") or "ticket")
        body = str(data.get("body") or "")
        prio = str(data.get("priority") or "normal")
        tid = tickets_svc.open_ticket(
            user_id, f"[{prio}] {subject}\n{body}", chat.id if chat else 0
        )
        return f"✅ تم فتح التذكرة #{tid}"

    if name == "wallet_topup":
        from app.services import market as market_svc

        amt = int(data.get("amount") or 0)
        bal = market_svc.wallet_topup(user_id, amt)
        return f"✅ تم الشحن. الرصيد الحالي: {bal}"

    if name == "vodafone_cash":
        from app.services import market as market_svc

        amount_cents = int(data.get("amount") or 0)
        ref = str(data.get("reference") or "").strip()
        photo = str(data.get("screenshot") or data.get("photo_file_id") or "")
        if hasattr(market_svc, "submit_vodafone_payment"):
            return market_svc.submit_vodafone_payment(
                user_id, amount_cents=amount_cents, reference=ref, photo_file_id=photo
            )
        return (
            f"⏳ تم استلام إثبات فودافون كاش\n"
            f"المبلغ: {amount_cents/100:.2f}\nالمرجع: {ref}\n"
            f"بانتظار تأكيد الإدارة (/vfcash_approve)."
        )

    if name == "pay_methods":
        method = str(data.get("method") or "")
        if method in ("فودافون كاش", "vodafone"):
            from app.flow_engine import start_flow
            # re-enter vodafone flow
            class _U:
                effective_message = update.effective_message
                effective_user = update.effective_user
                effective_chat = update.effective_chat
            await start_flow(update, context, "vodafone_cash")
            return "➡️ أكمل بيانات فودافون كاش"
        if method in ("رصيد المحفظة", "wallet"):
            from app.services import market as market_svc
            bal = market_svc.wallet_balance(user_id)
            return f"رصيد محفظتك: {bal}\nادفع من السلة بـ /cartcheckout بعد تفعيل الخصم من المحفظة."
        return (
            "لـ Telegram Payments: استخدم /buy أو /cartcheckout مع PAYMENT_PROVIDER_TOKEN "
            "في .env (من BotFather payments)."
        )

    if name == "coupon":

        from app.services import market as market_svc

        code = str(data.get("code") or "")
        return market_svc.coupon_apply_code(user_id, code, 0)

    return "تم."


# Commands that start flows (used by handlers)
FLOW_COMMANDS = {
    "addproduct": "add_product",
    "add_product": "add_product",
    "newticket": "open_ticket",
    "ticket": "open_ticket",
    "topup": "wallet_topup",
    "vfcash": "vodafone_cash",
    "vodafone": "vodafone_cash",
    "coupon": "coupon",
    "pay": "pay_methods",
    "paymethods": "pay_methods",
    "payment": "pay_methods",
}
