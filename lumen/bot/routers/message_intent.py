"""Text intent helpers for the Telegram message router.

Pure classification / lookup — no Telegram side-effects.
Junior engineers can change intent rules here without touching generation.
"""
from __future__ import annotations

import os
import re
from typing import Any

def _looks_like_generation_request(text: str) -> bool:
    """Explicit generate intent (verbs). Does NOT include bare bot-spec descriptions.

    Bare specs like «بوت متجر إلكتروني…» are handled by _looks_like_bot_spec and
    flows through free multi-agent engine (force_generate) — Gemini translate pipeline retired.
    """
    value = (text or "").strip().lower()
    # Strip decorative quotes/punctuation that users often paste from chat UIs.
    value = re.sub(r'["“”‘’«»٬،,]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return False
    if "بوت" not in value and "bot" not in value:
        return False
    return bool(
        re.search(
            r"(?:اعمل|عايز|عاوز|أريد|ابغى|أنشئ|انشئ|ابني|صمم|ولّد|ولد|سوي|سوى|generate|create|make|build).{0,80}(?:بوت|bot)"
            r"|(?:بوت|bot).{0,80}(?:ابدأ|ابدء|نفّذ|نفذ|ولّد|ولد|start|generate|create|make|build)",
            value,
            re.IGNORECASE,
        )
    )



_CONFIRM_ROOTS = {
    "أكد", "اكد", "تأكيد", "موافق", "نعم", "ايوه", "أيوه", "يلا",
    "ابدأ", "ابدا", "ابدء", "نفذ", "نفّذ", "انجز", "أنجز", "ولّد", "ولد",
    "تمام", "حاضر", "ماشي", "يلاا",
    "confirm", "yes", "ok", "start", "go", "generate", "done",
}
_CONFIRM_FILLER = {"و", "اللي", "على", "كده", "كدا", "بقوة", "فورا", "دلوقتي", "الآن", "الان", "يا", "رجاء", "please", "now"}


def _is_confirm_phrase(text: str) -> bool:
    """True for short go-ahead phrases like 'تمام ابدا وانجز' / 'ابدأ' / 'ok'."""
    value = (text or "").strip().lower()
    value = re.sub(r'["“”‘’«»٬،,!.?؟]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return False
    if value in _CONFIRM_ROOTS:
        return True
    tokens = re.findall(r"[\w\u0600-\u06ff]+", value)
    if not tokens or len(tokens) > 8:
        return False
    # Strip leading waw from tokens (وانجز → انجز)
    norm = []
    for t in tokens:
        if t.startswith("و") and len(t) > 2 and t[1:] in _CONFIRM_ROOTS:
            norm.append(t[1:])
        else:
            norm.append(t)
    useful = [t for t in norm if t not in _CONFIRM_FILLER]
    if not useful or len(useful) > 6:
        return False
    return all(t in _CONFIRM_ROOTS for t in useful) and any(t in _CONFIRM_ROOTS for t in useful)


def _prior_bot_request(user_data: dict | None) -> str:
    """Last generation-like user message from session history."""
    if not user_data:
        return ""
    explicit = str(user_data.get("last_bot_request") or "").strip()
    if explicit and _looks_like_generation_request(explicit):
        return explicit
    for item in reversed(list(user_data.get("chat_history") or [])):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if _looks_like_generation_request(content):
            return content
    return ""


# Public aliases (prefer these in new code)
looks_like_generation_request = _looks_like_generation_request
is_confirm_phrase = _is_confirm_phrase
prior_bot_request = _prior_bot_request

__all__ = [
    "looks_like_generation_request",
    "is_confirm_phrase",
    "prior_bot_request",
    "_looks_like_generation_request",
    "_is_confirm_phrase",
    "_prior_bot_request",
]
