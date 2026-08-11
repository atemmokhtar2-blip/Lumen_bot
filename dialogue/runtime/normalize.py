"""Arabic/English text normalization for robust matching."""
from __future__ import annotations

import re
import unicodedata

# Common Arabic free-variation
_ALEF = re.compile(r"[إأآا]")
_YAA = re.compile(r"[ىي]")
_TAA = re.compile(r"[ةه]")  # careful: only for matching, applied selectively
_TATWEEL = re.compile(r"\u0640")
_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670]")
_NON_ALNUM = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", str(text)).strip().lower()
    t = _DIACRITICS.sub("", t)
    t = _TATWEEL.sub("", t)
    t = _ALEF.sub("ا", t)
    t = _YAA.sub("ي", t)
    # keep ha/ta marbuta distinction lightly: map ة → ه for match only
    t = t.replace("ة", "ه")
    t = _NON_ALNUM.sub(" ", t)
    t = _SPACES.sub(" ", t).strip()
    return t


def tokens(text: str) -> list[str]:
    return [x for x in normalize(text).split() if x]
