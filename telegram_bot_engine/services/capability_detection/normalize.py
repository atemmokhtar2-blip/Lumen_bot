"""Arabic text normalization for capability matching.

Handles common dialect spelling, elongated letters, and leading hamza variants
so extractor/search don't miss real user phrasing.
"""
from __future__ import annotations

import re

# leading hamza/alef at token start → ا (preserves آلي mid-token)
_ALEF_LEAD = re.compile(r"(^|\s)[أإٱ]")  # exclude آ (آلي/قرآن)
_TEH_MARBUTA = re.compile(r"ة")
_TASHKEEL = re.compile(r"[\u064B-\u065F\u0670]")
_TATWEEL = re.compile(r"\u0640")
_ELONGATED = re.compile(r"(.)\1{2,}")

_TOKEN_MAP = {
    "الجداد": "الجدد",
    "اعضاء": "اعضاء",
    "الاعضاء": "الاعضاء",
    "الجروب": "الجروب",
    "جروب": "جروب",
    "كروب": "جروب",
    "يوزر": "مستخدم",
    "ادمن": "مشرف",
    "الادمن": "المشرف",
    "سبام": "spam",
    "تودو": "مهام",
    "todo": "مهام",
    "ليست": "قائمة",
    "صالون": "حجز",
    "تجميل": "حجز",
    "حلاق": "حجز",
    "باربر": "حجز",
    "عياده": "عيادة",
    "تصويت": "تصويت",
    "استبيان": "تصويت",
    "استبيانات": "تصويت",
    "اذاعه": "اعلان",
    "برودكاست": "اعلان",
    "جماعي": "اعلان",
    "صلاحيات": "صلاحيات",
    "ولاء": "نقاط",
    "مكافات": "نقاط",
    "مكافات": "نقاط",
    "احالة": "احالة",
    "ريفيرال": "احالة",
}


def normalize_ar(text: str) -> str:
    if not text:
        return ""
    t = text.strip().lower()
    t = _TASHKEEL.sub("", t)
    t = _TATWEEL.sub("", t)
    t = _ALEF_LEAD.sub(lambda m: m.group(1) + "ا", t)
    t = _TEH_MARBUTA.sub("ه", t)
    t = _ELONGATED.sub(r"\1\1", t)
    parts = re.split(r"(\s+)", t)
    out: list[str] = []
    for p in parts:
        if not p or p.isspace():
            out.append(p)
            continue
        out.append(_TOKEN_MAP.get(p, p))
    return "".join(out)


def expand_for_match(text: str) -> str:
    n = normalize_ar(text)
    extras: list[str] = []
    if any(w in n for w in ("صالون", "حلاق", "باربر", "تجميل")) or "حجز" in n:
        extras.append("حجز موعد booking")
    if "تصويت" in n or "استبيان" in n:
        extras.append("poll تصويت")
    if "اعلان" in n or "برودكاست" in n:
        extras.append("announce اذاعة اعلان")
    if "نقاط" in n or "ولاء" in n:
        extras.append("نقاط points balance leaderboard")
    if "احاله" in n or "احالة" in n or "ريفيرال" in n:
        extras.append("احالة referral")
    if "صلاحيات" in n or "مشرف" in n:
        extras.append("admin مشرف صلاحيات")
    if "مهام" in n or "تودو" in n:
        extras.append("مهام tasks todo")
    if "عمله" in n or "عمله" in n or ("تحويل" in n and "عمل" in n):
        extras.append("عمله currency")
    if extras:
        return n + " " + " ".join(extras)
    return n


__all__ = ["normalize_ar", "expand_for_match"]
