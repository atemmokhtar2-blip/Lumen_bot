"""UX labels + short slash commands."""
from __future__ import annotations

FEATURE_UX: dict[str, tuple[str, str, str]] = {
    "start": ("البداية", "Start", "start"),
    "help": ("المساعدة", "Help", "help"),
    "about": ("عن البوت", "About", "about"),
    "shop_catalog": ("المنتجات", "Products", "shop"),
    "flash_sale_list": ("العروض", "Offers", "flash"),
    "shop_order": ("طلب منتج", "Order", "order"),
    "order_track": ("متابعة الطلب", "Track", "track"),
    "cart_add": ("أضف للسلة", "Add", "add"),
    "cart_view": ("السلة", "Cart", "cart"),
    "cart_checkout": ("إتمام الطلب", "Checkout", "checkout"),
    "shop_my_orders": ("طلباتي", "Orders", "orders"),
    "product_search": ("بحث", "Search", "search"),
    "product_info": ("تفاصيل", "Info", "product"),
    "pay_methods": ("الدفع", "Pay", "pay"),
    "wallet_balance": ("المحفظة", "Wallet", "wallet"),
    "wishlist_view": ("المفضلة", "Wishlist", "wishlist"),
    "coupon_apply": ("كوبون", "Coupon", "coupon"),
    "faq_show": ("التواصل", "Contact", "contact"),
}

def label(fid: str, lang: str = "ar") -> str:
    ar, en, _ = FEATURE_UX.get(fid, (fid.replace("_", " "), fid.replace("_", " "), fid))
    return ar if (lang or "ar").lower().startswith("ar") else en

def slash(fid: str) -> str:
    e = FEATURE_UX.get(fid)
    return e[2] if e else "".join(c for c in (fid or "").lower() if c.isalnum())[:24] or "cmd"

def menu_desc(fid: str, lang: str = "ar") -> str:
    return label(fid, lang)[:48]
