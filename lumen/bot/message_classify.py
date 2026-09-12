"""Strict classification of user messages — prevents env/token/chat confusion.

Rules (fail-closed):
  - Bot tokens and GitHub PATs are NEVER env values.
  - Free-form Arabic/English chat is NEVER an env value.
  - Env values only accepted in explicit configure mode with type checks.
  - Host/run always resolve a real on-disk path before proceeding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from lumen.platform.token_patterns import (
    looks_like_bot_token,
    looks_like_github_pat,
    normalize_bot_token,
)


class MessageKind(str, Enum):
    BOT_TOKEN = "bot_token"
    GITHUB_PAT = "github_pat"
    ENV_VALUE = "env_value"
    CHAT = "chat"
    EMPTY = "empty"


@dataclass(frozen=True)
class ClassifiedMessage:
    kind: MessageKind
    normalized: str
    reason: str = ""


# Conversational / intent markers — never env
_CHAT_MARKERS = (
    "اعمل", "أسحب", "اسحب", "شغّل", "شغل", "استضف", "انشر", "تعديل",
    "أضف", "اضف", "حذف", "اشرح", "فهم", "حلل", "بوت", "مستودع", "ريبو",
    "clone", "deploy", "host", "generate", "help", "مساعدة",
)
_NUMERIC_ENV_HINTS = (
    "TIMEOUT", "SECONDS", "LIMIT", "BURST", "SIZE", "PORT", "COUNT", "MAX",
    "MIN", "TTL", "DELAY", "INTERVAL", "RATE", "MB", "KB",
)


def normalize_ws(text: str) -> str:
    return normalize_bot_token(text)



# looks_like_bot_token imported from lumen.platform.token_patterns



def looks_like_pat(text: str) -> bool:
    return looks_like_github_pat(text)



def looks_like_chat(text: str) -> bool:
    v = (text or "").strip()
    if not v:
        return False
    if looks_like_bot_token(v) or looks_like_pat(v):
        return False
    if len(v) > 80 and v.count(" ") >= 3:
        return True
    if any(ch in v for ch in "؟?!"):
        return True
    low = v.lower()
    if any(m in low for m in _CHAT_MARKERS):
        return True
    # Arabic letters density
    ar = sum(1 for c in v if "\u0600" <= c <= "\u06FF")
    if ar >= 6 and v.count(" ") >= 2:
        return True
    return False


def is_plausible_env_value(var_name: str, value: str) -> bool:
    """Strict: only short machine-like values, typed by variable name."""
    v = (value or "").strip()
    name = (var_name or "").strip().upper()
    if not v or not name or len(v) > 200:
        return False
    if looks_like_bot_token(v) or looks_like_pat(v):
        return False
    if looks_like_chat(v):
        return False
    if "\n" in v or "\r" in v:
        return False
    if v.count(" ") >= 3:
        return False
    if any(h in name for h in _NUMERIC_ENV_HINTS):
        try:
            float(v.replace("_", ""))
        except ValueError:
            return False
        return True
    # generic: no spaces, printable, not a sentence
    if " " in v and not (v.startswith("http://") or v.startswith("https://")):
        # allow single-space tokens only for non-numeric
        if v.count(" ") > 1:
            return False
    return True


def classify(text: str, *, pending_env_var: str = "") -> ClassifiedMessage:
    raw = (text or "").strip()
    if not raw:
        return ClassifiedMessage(MessageKind.EMPTY, "", "empty")
    if looks_like_bot_token(raw):
        return ClassifiedMessage(MessageKind.BOT_TOKEN, normalize_ws(raw), "bot_token")
    if looks_like_pat(raw):
        return ClassifiedMessage(MessageKind.GITHUB_PAT, raw.strip(), "pat")
    if pending_env_var and is_plausible_env_value(pending_env_var, raw):
        return ClassifiedMessage(MessageKind.ENV_VALUE, raw.strip(), f"env:{pending_env_var}")
    return ClassifiedMessage(MessageKind.CHAT, raw, "chat")


def resolve_on_disk_path(
    user_data: dict[str, Any] | None = None,
    pending: dict[str, Any] | None = None,
) -> str:
    from lumen.platform.project_paths import resolve_on_disk_path as _r
    return _r(user_data, pending)



__all__ = [
    "MessageKind",
    "ClassifiedMessage",
    "classify",
    "looks_like_bot_token",
    "looks_like_pat",
    "looks_like_chat",
    "is_plausible_env_value",
    "resolve_on_disk_path",
    "normalize_ws",
]
