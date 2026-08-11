"""Cross-domain entity extraction — shop, security, edu, devops, zero ML."""
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
    # commerce
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
    brand_analogy: str | None = None
    # security / infra
    target_domain: str | None = None
    target_ip: str | None = None
    target_url: str | None = None
    email: str | None = None
    security_checks: list[str] = field(default_factory=list)
    # education
    course_topic: str | None = None
    # devops / iot
    tech_stack: list[str] = field(default_factory=list)
    # generic
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
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
            "target_domain": self.target_domain,
            "target_ip": self.target_ip,
            "target_url": self.target_url,
            "email": self.email,
            "security_checks": list(self.security_checks),
            "course_topic": self.course_topic,
            "tech_stack": list(self.tech_stack),
        }
        return {k: v for k, v in d.items() if v not in (None, [], False)}


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
_PRODUCT = [
    re.compile(r"(?:يبيع|بيع|لبيع|selling|sells?)\s+([^\n،,.]{2,60})", re.I),
    re.compile(r"(?:منتجات?|products?)\s+([^\n،,.]{2,60})", re.I),
    re.compile(r"(?:متجر|محل|shop|store)\s+([^\n،,.]{2,40})", re.I),
]
_QTY = [re.compile(r"(\d+)\s*(?:منتج|منتجات|item|items|users|مستخدم|مستخدمين|قطعة)", re.I)]
_CURRENCY = re.compile(r"\b(EGP|USD|SAR|AED|EUR|GBP|جنيه|دولار|ريال|درهم|يورو)\b", re.I)

_DOMAIN_RE = re.compile(
    r"\b(?:(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,})\b", re.I
)
_IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b")
_URL_RE = re.compile(r"https?://[^\s]+", re.I)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

_SEC_CHECKS = {
    "dns": ["dns", "سجلات dns", "dns records", "a record", "cname"],
    "mx": ["mx", "mail exchange", "سجلات mx"],
    "spf": ["spf", "sender policy"],
    "dmarc": ["dmarc"],
    "tls": ["tls", "ssl", "شهادة", "certificate", "https"],
    "headers": ["headers", "security headers", "hsts", "csp"],
    "whois": ["whois"],
    "phishing": ["phishing", "تصيد", "تصيّد"],
    "port_scan": ["port scan", "منافذ", "ports"],
    "malware": ["malware", "فيروس", "virus"],
}

_TECH = {
    "docker": ["docker", "dockerfile", "حاوية"],
    "kubernetes": ["kubernetes", "k8s"],
    "mqtt": ["mqtt"],
    "arduino": ["arduino"],
    "esp32": ["esp32"],
    "postgres": ["postgres", "postgresql"],
    "redis": ["redis"],
    "nginx": ["nginx"],
}

_PAY_MAP = {
    "visa": ["فيزا", "visa", "بطاقة", "card", "mastercard", "ماستركارد", "ميزا"],
    "vodafone_cash": ["فودافون كاش", "فودافون", "vodafone cash", "vodafone"],
    "fawry": ["فوري كاش", "فوري", "fawry"],
    "orange_cash": ["اورنج كاش", "أورنج كاش", "orange cash"],
    "instapay": ["instapay", "انستا باي", "انستاباي"],
    "wallet": ["محفظة", "محفظه", "wallet", "رصيد"],
    "telegram_payments": ["telegram payments", "دفع تيليجرام", "invoice"],
    "cod": ["دفع عند الاستلام", "عند الاستلام", "cod", "cash on delivery"],
    "stripe": ["stripe", "سترايب"],
    "paypal": ["paypal", "باي بال", "بايبال"],
}

_CITIES = [
    "القاهرة", "القاهره", "الجيزة", "الجيزه", "الإسكندرية", "الاسكندرية", "اسكندرية",
    "المنصورة", "طنطا", "أسيوط", "أسوان", "cairo", "giza", "alexandria",
]
_BRANDS = {
    "amazon": ["امازون", "أمازون", "amazon"],
    "noon": ["نون", "noon"],
    "jumia": ["جوميا", "jumia"],
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

    for rx in _PRODUCT:
        m = rx.search(raw)
        if m:
            prod = m.group(1).strip()
            prod = re.split(
                r"(?:وفيه|فيه|مع|with|and|\+|فيزا|فودافون|فوري|visa|تقييم|توصيل|شحن)",
                prod,
                maxsplit=1,
            )[0].strip(" +،,")
            if len(prod) >= 2:
                ent.product = prod[:80]
            break

    for cat, words in _categories().items():
        for w in words:
            if normalize_text(w) in norm or w.lower() in low:
                ent.category = cat
                if not ent.product and cat not in {"أمن سيبراني", "دورات"}:
                    ent.product = cat
                if cat == "أمن سيبراني":
                    ent.product = None
                break
        if ent.category:
            break

    if re.search(r"(?:لأطفال|اطفال|أطفال|kids|children|baby|بيبي)", raw, re.I):
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

    for city in _CITIES:
        if city in raw or city.lower() in low:
            ent.city = city
            break

    for method, keys in _PAY_MAP.items():
        if any(k in low or k in raw or normalize_text(k) in norm for k in keys):
            if method not in ent.payment_methods:
                ent.payment_methods.append(method)

    if any(k in raw or k in low for k in ("توصيل", "شحن", "delivery", "shipping", "courier", "مندوب")):
        ent.wants_delivery = True
    if any(k in raw or k in low for k in ("خصم", "كوبون", "coupon", "discount", "تخفيض")):
        ent.wants_discounts = True
    if any(k in raw or k in low for k in ("محفظة", "محفظه", "wallet", "رصيد")):
        ent.wants_wallet = True
    if any(k in raw or k in low for k in ("تقييم", "مراجعة", "review", "rating")):
        ent.wants_reviews = True
    if any(k in raw or k in low for k in ("مخزون", "stock", "inventory")):
        ent.wants_inventory = True

    for brand, keys in _BRANDS.items():
        if any(k in raw or k in low for k in keys):
            ent.brand_analogy = brand
            break

    # Security / network entities
    um = _URL_RE.search(raw)
    if um:
        ent.target_url = um.group(0)[:200]
    dm = _DOMAIN_RE.search(raw)
    if dm:
        cand = dm.group(0).lower()
        # skip emails
        if "@" not in cand and not cand.endswith((".jpg", ".png", ".gif")):
            ent.target_domain = cand
    ipm = _IP_RE.search(raw)
    if ipm:
        ent.target_ip = ipm.group(0)
    em = _EMAIL_RE.search(raw)
    if em:
        ent.email = em.group(0)

    for check, keys in _SEC_CHECKS.items():
        if any(k in low or k in raw for k in keys):
            if check not in ent.security_checks:
                ent.security_checks.append(check)

    # Education topic
    m = re.search(r"(?:كورس|دورة|course|درس)\s+([^\n،,.]{2,40})", raw, re.I)
    if m:
        ent.course_topic = m.group(1).strip()[:60]

    for tech, keys in _TECH.items():
        if any(k in low or k in raw for k in keys):
            if tech not in ent.tech_stack:
                ent.tech_stack.append(tech)

    return ent


__all__ = ["ExtractedEntities", "extract_entities"]
