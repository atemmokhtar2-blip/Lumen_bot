"""Entity extraction from user text — regex + rules, zero ML."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedEntities:
    product: str | None = None
    audience: str | None = None
    price_max: float | None = None
    price_min: float | None = None
    quantity: int | None = None
    currency: str | None = None
    payment_methods: list[str] = field(default_factory=list)
    wants_delivery: bool = False
    wants_discounts: bool = False
    wants_wallet: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product,
            "audience": self.audience,
            "price_max": self.price_max,
            "price_min": self.price_min,
            "quantity": self.quantity,
            "currency": self.currency,
            "payment_methods": list(self.payment_methods),
            "wants_delivery": self.wants_delivery,
            "wants_discounts": self.wants_discounts,
            "wants_wallet": self.wants_wallet,
            **{k: v for k, v in self.raw.items() if k not in {
                "product", "audience", "price_max", "price_min", "quantity", "currency"
            }},
        }


_PRICE_MAX = [
    re.compile(r"(?:أقل من|اقل من|تحت|below|under|max|أقصى|اقصى)\s*(\d+(?:[.,]\d+)?)", re.I),
    re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:جنيه|ج\.?\s*م|EGP|\$|دولار)", re.I),
]
_PRICE_MIN = [
    re.compile(r"(?:أكتر من|اكتر من|أكثر من|اكثر من|فوق|above|over|min)\s*(\d+(?:[.,]\d+)?)", re.I),
]
_PRODUCT = [
    re.compile(r"(?:يبيع|بيع|لبيع|selling|sells?)\s+([^\n،,.]{2,50})", re.I),
    re.compile(r"(?:منتجات?|products?)\s+([^\n،,.]{2,50})", re.I),
]
_AUDIENCE = [
    re.compile(r"(?:لأطفال|للاطفال|اطفال|أطفال)", re.I),
    re.compile(r"(?:للنساء|حريمي|نسائي)", re.I),
    re.compile(r"(?:للرجال|رجالي)", re.I),
    re.compile(r"(?:for\s+kids|for\s+children)", re.I),
]
_QTY = [
    re.compile(r"(\d+)\s*(?:منتج|منتجات|item|items|users|مستخدم|مستخدمين)", re.I),
]
_CURRENCY = re.compile(r"\b(EGP|USD|SAR|AED|EUR|جنيه|دولار|ريال|درهم)\b", re.I)

_PAY_MAP = {
    "visa": ["فيزا", "visa", "بطاقة", "card", "mastercard", "ماستركارد"],
    "vodafone_cash": ["فودافون", "vodafone", "كاش فودافون", "vf cash"],
    "wallet": ["محفظة", "wallet", "رصيد"],
    "telegram_payments": ["telegram payments", "دفع تيليجرام", "مدفوعات تيليجرام", "invoice"],
    "cod": ["دفع عند الاستلام", "cod", "عند الاستلام"],
}


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None


def extract_entities(text: str, patterns: dict | None = None) -> ExtractedEntities:
    raw = text or ""
    low = raw.lower()
    ent = ExtractedEntities()

    for rx in _PRICE_MAX:
        m = rx.search(raw)
        if m:
            ent.price_max = _to_float(m.group(1))
            break
    for rx in _PRICE_MIN:
        m = rx.search(raw)
        if m:
            ent.price_min = _to_float(m.group(1))
            break
    for rx in _PRODUCT:
        m = rx.search(raw)
        if m:
            ent.product = m.group(1).strip()[:80]
            break
    if re.search(r"(?:لأطفال|للاطفال|اطفال|أطفال|kids|children)", raw, re.I):
        ent.audience = "أطفال"
    elif re.search(r"(?:للنساء|حريمي|نسائي|women)", raw, re.I):
        ent.audience = "نساء"
    elif re.search(r"(?:للرجال|رجالي|men)", raw, re.I):
        ent.audience = "رجال"
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

    for method, keys in _PAY_MAP.items():
        if any(k in low or k in raw for k in keys):
            ent.payment_methods.append(method)

    if any(k in raw or k in low for k in ("توصيل", "شحن", "delivery", "shipping")):
        ent.wants_delivery = True
    if any(k in raw or k in low for k in ("خصم", "كوبون", "coupon", "discount", "تخفيض")):
        ent.wants_discounts = True
    if any(k in raw or k in low for k in ("محفظة", "wallet", "رصيد")):
        ent.wants_wallet = True

    return ent


__all__ = ["ExtractedEntities", "extract_entities"]
