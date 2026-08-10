"""Sanitize secrets/paths for job storage and API responses."""
from __future__ import annotations

import re

_TG_TOKEN = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b")
_GH_TOKEN = re.compile(r"\b(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{10,}\b")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{12,}")
_API_KEY = re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([^\s'\"]{8,})")
_ABS_PATH = re.compile(r"(/(?:home|tmp|var|app|usr|opt|root)/[^\s:\"']+)")


def sanitize_error(text: str, *, max_len: int = 200) -> str:
    s = str(text or "")
    s = _TG_TOKEN.sub("[REDACTED_TELEGRAM_TOKEN]", s)
    s = _GH_TOKEN.sub("[REDACTED_GITHUB_TOKEN]", s)
    s = _BEARER.sub(r"\1[REDACTED]", s)
    s = _API_KEY.sub(r"\1=[REDACTED]", s)
    s = _ABS_PATH.sub("[PATH]", s)
    return s.replace("\x00", "")[: max(0, int(max_len))]


def sanitize_for_storage(text: str, *, max_len: int = 500) -> str:
    return sanitize_error(text, max_len=max_len)
