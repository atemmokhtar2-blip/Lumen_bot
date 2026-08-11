"""Arabic/English text normalization — pure Python, zero ML."""
from __future__ import annotations

import re
import unicodedata

# Arabic letter variants → canonical
_ALEF = re.compile(r"[إأآٱ]")
_YEH = re.compile(r"[ىي]")
_TEH = re.compile(r"ة")
_WAW = re.compile(r"ؤ")
_HAMZA = re.compile(r"[ءئ]")
_TATWEEL = re.compile(r"ـ+")
_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_SPACES = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s\u0600-\u06FF]+", re.UNICODE)


def strip_diacritics(text: str) -> str:
    return _DIACRITICS.sub("", text or "")


def normalize_arabic_letters(text: str) -> str:
    t = text or ""
    t = _ALEF.sub("ا", t)
    t = _YEH.sub("ي", t)
    t = _TEH.sub("ه", t)
    t = _WAW.sub("و", t)
    t = _HAMZA.sub("", t)
    t = _TATWEEL.sub("", t)
    return t


def normalize_text(text: str) -> str:
    """Full normalize for matching: NFKC, Arabic letters, lower, collapse space."""
    t = unicodedata.normalize("NFKC", text or "")
    t = strip_diacritics(t)
    t = normalize_arabic_letters(t)
    t = t.lower()
    t = _PUNCT.sub(" ", t)
    t = _SPACES.sub(" ", t).strip()
    return t


def tokenize(text: str) -> list[str]:
    t = normalize_text(text)
    if not t:
        return []
    return [w for w in t.split(" ") if w]


__all__ = ["normalize_text", "tokenize", "strip_diacritics", "normalize_arabic_letters"]
