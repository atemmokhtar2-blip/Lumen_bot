"""Arabic/English normalization — dialect-aware, zero ML."""
from __future__ import annotations

import re
import unicodedata

_ALEF = re.compile(r"[إأآٱ]")
_YEH = re.compile(r"[ىي]")
_TEH = re.compile(r"ة")
_WAW_HAMZA = re.compile(r"[ؤ]")
_YEH_HAMZA = re.compile(r"[ئ]")
_HAMZA = re.compile(r"ء")
_TATWEEL = re.compile(r"ـ+")
_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_SPACES = re.compile(r"\s+")
# keep digits and letters
_PUNCT = re.compile(r"[^\w\s\u0600-\u06FF]+", re.UNICODE)

# Egyptian / Gulf common elongations and slang reductions
_ELONGATION = re.compile(r"(.)\1{2,}")  # يلاااا → يلاا
_DIALECT_MAP = {
    "احذيه": "احذية",
    "أحذيه": "احذية",
    "هدومات": "ملابس",
    "هدوم": "ملابس",
    "موبايلاات": "موبايلات",
    "ععايز": "عايز",
    "عاويز": "عايز",
    "ابغا": "ابغى",
    "متججر": "متجر",
    "متجرر": "متجر",
    "فودفون": "فودافون",
    "فودافونكاش": "فودافون كاش",
    "فوريكاش": "فوري كاش",
    "انستاباي": "instapay",
    "امازون": "امازون",
    "شوب": "shop",
    "shope": "shop",
    "storee": "store",
}


def strip_diacritics(text: str) -> str:
    return _DIACRITICS.sub("", text or "")


def normalize_arabic_letters(text: str) -> str:
    t = text or ""
    t = _ALEF.sub("ا", t)
    t = _YEH.sub("ي", t)
    t = _TEH.sub("ه", t)
    t = _WAW_HAMZA.sub("و", t)
    t = _YEH_HAMZA.sub("ي", t)
    t = _HAMZA.sub("", t)
    t = _TATWEEL.sub("", t)
    return t


def apply_dialect_map(text: str) -> str:
    t = text or ""
    low = t.lower()
    for src, dst in _DIALECT_MAP.items():
        if src in t or src in low:
            t = re.sub(re.escape(src), dst, t, flags=re.I)
    return t


def light_stem_ar(token: str) -> str:
    """Very light Arabic stem: strip common prefixes/suffixes for matching."""
    t = token or ""
    if len(t) < 4:
        return t
    for pref in ("ال", "وال", "بال", "كال", "فال"):
        if t.startswith(pref) and len(t) - len(pref) >= 3:
            t = t[len(pref) :]
            break
    for suf in ("ات", "ين", "ون", "ان", "ها", "هم", "كم", "كن"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            t = t[: -len(suf)]
            break
    return t


def normalize_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = strip_diacritics(t)
    t = apply_dialect_map(t)
    t = normalize_arabic_letters(t)
    t = _ELONGATION.sub(r"\1\1", t)
    t = t.lower()
    t = _PUNCT.sub(" ", t)
    t = _SPACES.sub(" ", t).strip()
    return t


def tokenize(text: str) -> list[str]:
    t = normalize_text(text)
    if not t:
        return []
    return [w for w in t.split(" ") if w]


def tokenize_stemmed(text: str) -> list[str]:
    return [light_stem_ar(w) for w in tokenize(text)]


__all__ = [
    "normalize_text",
    "tokenize",
    "tokenize_stemmed",
    "strip_diacritics",
    "normalize_arabic_letters",
    "light_stem_ar",
    "apply_dialect_map",
]
