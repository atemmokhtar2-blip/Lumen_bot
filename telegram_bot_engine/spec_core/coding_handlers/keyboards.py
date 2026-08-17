"""Emit handlers, keyboards, main.py registration for generated bots."""
from __future__ import annotations

from ..coding_emit_foundation import _msg
from ..registry import get_capability
from ..schema import BotSpec, Feature

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
        "clinic_book": ("🏥 حجز موعد طبي", "🏥 Book clinic", "clinicbook"),
        "clinic_my": ("📅 مواعيدي", "📅 My appointments", "clinicmy"),
        "clinic_cancel": ("❌ إلغاء موعد", "❌ Cancel appt", "cliniccancel"),
        "clinic_slots": ("🕐 المواعيد المتاحة", "🕐 Available slots", "clinicslots"),
        "book_slot": ("📌 حجز موعد", "📌 Book slot", "bookslot"),
        "book_list": ("📋 حجوزاتي", "📋 My bookings", "booklist"),
        "book_cancel": ("❎ إلغاء حجز", "❎ Cancel booking", "bookcancel"),
        "ticket_open": ("🎫 فتح تذكرة", "🎫 Open ticket", "ticketopen"),
        "ticket_list": ("📬 التذاكر", "📬 Tickets", "ticketlist"),
        "ticket_status": ("🔎 حالة تذكرة", "🔎 Ticket status", "ticketstatus"),
        "sec_dns_check": ("🔎 فحص DNS", "🔎 DNS check", "secdnscheck"),
        "sec_tls_check": ("🔒 فحص SSL", "🔒 TLS check", "sectlscheck"),
        "sec_domain_overview": ("🌐 فحص النطاق", "🌐 Domain overview", "secdomainoverview"),
        "user_ban": ("🚫 حظر", "🚫 Ban", "ban"),
        "user_mute": ("🔇 كتم", "🔇 Mute", "mute"),
        "user_kick": ("👢 طرد", "👢 Kick", "kick"),
        "user_warn": ("⚠️ تحذير", "⚠️ Warn", "warn"),
        "user_unmute": ("🔊 فك الكتم", "🔊 Unmute", "unmute"),
        "user_unban": ("✅ فك الحظر", "✅ Unban", "unban"),
        "user_info": ("ℹ️ معلومات", "ℹ️ Info", "info"),
        "welcome_set": ("👋 ترحيب", "👋 Welcome", "welcome"),
        "rules": ("📜 القوانين", "📜 Rules", "rules"),

        "task_add": ("➕ إضافة مهمة", "➕ Add task", "add"),
        "task_list": ("📋 مهامي", "📋 My tasks", "list"),
        "task_delete": ("🗑️ حذف مهمة", "🗑️ Delete task", "delete"),
        "task_done": ("✅ إنهاء مهمة", "✅ Done task", "done"),
        "task_clear": ("🧹 مسح المنتهية", "🧹 Clear done", "clear"),
        "remind_set": ("⏰ تذكير", "⏰ Set reminder", "remindset"),
        "remind_list": ("🔔 تذكيراتي", "🔔 My reminders", "remindlist"),
        "note_add": ("📝 ملاحظة", "📝 Add note", "note"),
        "note_list": ("📒 ملاحظاتي", "📒 My notes", "notes"),
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


