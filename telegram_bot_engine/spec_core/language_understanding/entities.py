"""Rich entity extraction — products, audience, money, payments, geo, zero ML."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .normalize import normalize_text

_DATA = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=1)
def _categories() -> dict[str, list[str]]:
    path = _DATA / "product_categories.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


@dataclass
class ExtractedEntities:
    product: str | None = None
    category: str | None = None
    audience: str | None = None
    price_max: float | None = None
    price_min: float | None = None
    quantity: int | None = None
    currency: str | None = None
    city: str | None = None
    payment_methods: list[str] = field(default_factory=list)
    wants_delivery: bool = False
    wants_discounts: bool = False
    wants_wallet: bool = False
    wants_reviews: bool = False
    wants_inventory: bool = False
    brand_analogy: str | None = None  # amazon, noon, ...
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product,
            "category": self.category,
            "audience": self.audience,
            "price_max": self.price_max,
            "price_min": self.price_min,
            "quantity": self.quantity,
            "currency": self.currency,
            "city": self.city,
            "payment_methods": list(self.payment_methods),
            "wants_delivery": self.wants_delivery,
            "wants_discounts": self.wants_discounts,
            "wants_wallet": self.wants_wallet,
            "wants_reviews": self.wants_reviews,
            "wants_inventory": self.wants_inventory,
            "brand_analogy": self.brand_analogy,
        }


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None


_PRICE_MAX = [
    re.compile(r"(?:أقل من|اقل من|تحت|below|under|max|أقصى|اقصى)\s*(\d+(?:[.,]\d+)?)", re.I),
    re.compile(r"under\s*(\d+(?:[.,]\d+)?)", re.I),
    re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:جنيه|ج\.?\s*م|EGP|\$|دولار|ريال|درهم|SAR|AED|USD)", re.I),
]
_PRICE_MIN = [
    re.compile(r"(?:أكتر من|اكتر من|أكثر من|اكثر من|فوق|above|over|min|من)\s*(\d+(?:[.,]\d+)?)", re.I),
]
_PRODUCT = [
    re.compile(r"(?:يبيع|بيع|لبيع|selling|sells?)\s+([^\n،,.]{2,60})", re.I),
    re.compile(r"(?:منتجات?|products?)\s+([^\n،,.]{2,60})", re.I),
    re.compile(r"(?:متجر|محل|shop|store)\s+([^\n،,.]{2,40})", re.I),
]
_QTY = [
    re.compile(r"(\d+)\s*(?:منتج|منتجات|item|items|users|مستخدم|مستخدمين|قطعة|قطعه)", re.I),
]
_CURRENCY = re.compile(
    r"\b(EGP|USD|SAR|AED|EUR|GBP|جنيه|دولار|ريال|درهم|يورو)\b", re.I
)

_PAY_MAP: dict[str, list[str]] = {
    "visa": ["فيزا", "visa", "بطاقة", "بطاقه", "card", "mastercard", "ماستركارد", "ميزا"],
    "vodafone_cash": ["فودافون كاش", "فودافون", "vodafone cash", "vodafone", "vf cash"],
    "fawry": ["فوري كاش", "فوري", "fawry"],
    "orange_cash": ["اورنج كاش", "أورنج كاش", "orange cash"],
    "etisalat_cash": ["اتصالات كاش", "etisalat cash"],
    "instapay": ["instapay", "انستا باي", "انستاباي"],
    "wallet": ["محفظة", "محفظه", "wallet", "رصيد"],
    "telegram_payments": [
        "telegram payments", "دفع تيليجرام", "مدفوعات تيليجرام", "invoice", "ستارا",
    ],
    "cod": ["دفع عند الاستلام", "عند الاستلام", "cod", "cash on delivery", "كاش اون ديليفري"],
    "apple_pay": ["apple pay", "آبل باي"],
    "google_pay": ["google pay", "جوجل باي"],
}

_CITIES = [
    "القاهرة", "القاهره", "الجيزة", "الجيزه", "الإسكندرية", "الاسكندرية", "اسكندرية",
    "المنصورة", "طنطا", "أسيوط", "اسيوط", "أسوان", "اسوان", "الغردقة", "شرم",
    "cairo", "giza", "alexandria",
]

_BRANDS = {
    "amazon": ["امازون", "أمازون", "amazon"],
    "noon": ["نون", "noon"],
    "jumia": ["جوميا", "jumia"],
    "talabat": ["طلبات", "talabat"],
    "shopify": ["شوبيفاي", "shopify"],
}


def extract_entities(text: str) -> ExtractedEntities:
    raw = text or ""
    norm = normalize_text(raw)
    low = raw.lower()
    ent = ExtractedEntities()

    for rx in _PRICE_MAX:
        m = rx.search(raw) or rx.search(norm)
        if m:
            ent.price_max = _to_float(m.group(1))
            break
    for rx in _PRICE_MIN:
        m = rx.search(raw)
        if m:
            # avoid matching "من 5 منتجات" as price_min loosely — require currency or under/over words
            if re.search(r"(أكثر|اكثر|أكتر|اكتر|فوق|above|over|min)", m.group(0), re.I):
                ent.price_min = _to_float(m.group(1))
                break

    for rx in _PRODUCT:
        m = rx.search(raw)
        if m:
            prod = m.group(1).strip()
            # trim trailing payment/delivery/review chatter
            prod = re.split(
                r"(?:وفيه|فيه|مع|with|and|\+|فيزا|فودافون|فوري|visa|تقييم|توصيل|شحن)",
                prod,
                maxsplit=1,
            )[0].strip(" +،,")
            if len(prod) >= 2:
                ent.product = prod[:80]
            break

    # categories lexicon
    cats = _categories()
    for cat, words in cats.items():
        for w in words:
            if normalize_text(w) in norm or w in raw:
                ent.category = cat
                if not ent.product:
                    ent.product = cat
                break
        if ent.category:
            break

    if re.search(r"(?:لأطفال|للاطفال|اطفال|أطفال|kids|children|baby|بيبي)", raw, re.I):
        ent.audience = "أطفال"
    elif re.search(r"(?:للنساء|حريمي|نسائي|women|ladies)", raw, re.I):
        ent.audience = "نساء"
    elif re.search(r"(?:للرجال|رجالي|men|رجاله)", raw, re.I):
        ent.audience = "رجال"
    elif re.search(r"(?:شباب|teen)", raw, re.I):
        ent.audience = "شباب"

    for rx in _QTY:
        m = rx.search(raw)
        if m:
            try:
                ent.quantity = int(m.group(1))
            except Exception:
                pass
            break

    m = _CURRENCY.search(raw)
    if m:
        ent.currency = m.group(1)

    for city in _CITIES:
        if city in raw or city.lower() in low:
            ent.city = city
            break

    for method, keys in _PAY_MAP.items():
        if any(k in low or k in raw or normalize_text(k) in norm for k in keys):
            if method not in ent.payment_methods:
                ent.payment_methods.append(method)

    if any(
        k in raw or k in low or normalize_text(k) in norm
        for k in ("توصيل", "شحن", "delivery", "shipping", "courier", "مندوب")
    ):
        ent.wants_delivery = True
    if any(k in raw or k in low for k in ("خصم", "كوبون", "coupon", "discount", "تخفيض", "عرض")):
        ent.wants_discounts = True
    if any(k in raw or k in low for k in ("محفظة", "محفظه", "wallet", "رصيد")):
        ent.wants_wallet = True
    if any(k in raw or k in low for k in ("تقييم", "مراجعة", "review", "rating", "نجوم")):
        ent.wants_reviews = True
    if any(k in raw or k in low for k in ("مخزون", "stock", "inventory", "كمية")):
        ent.wants_inventory = True

    for brand, keys in _BRANDS.items():
        if any(k in raw or k in low for k in keys):
            # "زي امازون" style
            if re.search(rf"(?:زي|مثل|like|as)\s*.{{0,8}}{re.escape(keys[0])}", raw, re.I) or any(
                k in raw for k in keys
            ):
                ent.brand_analogy = brand
                break

    return ent


__all__ = ["ExtractedEntities", "extract_entities"]
