"""Sanitize secrets/paths for job storage and API responses."""
from __future__ import annotations

import re

_TG_TOKEN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
_GH_TOKEN = re.compile(r"\b(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{10,}\b")
_STRIPE = re.compile(r"\b(sk_live_|sk_test_|pk_live_|pk_test_|whsec_)[A-Za-z0-9]+")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{12,}")
_API_KEY = re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)\s*[:=]\s*['\"]?([^\s'\"]{8,})")
_ABS_PATH = re.compile(r"(/(?:home|tmp|var|app|usr|opt|root|Users|private)[^\s:\"']*)")
_WIN_PATH = re.compile(r"(?i)\b([A-Z]:\\[^\s\"']+)")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_AWS = re.compile(r"\b(AKIA[0-9A-Z]{16})\b")
_AWS_SECRET = re.compile(r"(?i)(aws_secret_access_key|secret_access_key)\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{20,})")
# Long high-entropy tokens (generic)
_LONG_SECRET = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")
_HEX_SECRET = re.compile(r"\b[a-fA-F0-9]{32,}\b")
_BASE64_BLOB = re.compile(r"\b[A-Za-z0-9+/]{48,}={0,2}\b")


def sanitize_error(text: str, *, max_len: int = 200) -> str:
    s = str(text or "")
    s = _TG_TOKEN.sub("[REDACTED_TELEGRAM_TOKEN]", s)
    s = _GH_TOKEN.sub("[REDACTED_GITHUB_TOKEN]", s)
    s = _STRIPE.sub("[REDACTED_STRIPE_KEY]", s)
    s = _JWT.sub("[REDACTED_JWT]", s)
    s = _AWS.sub("[REDACTED_AWS_KEY]", s)
    s = _AWS_SECRET.sub(r"\1=[REDACTED]", s)
    s = _BEARER.sub(r"\1[REDACTED]", s)
    s = _API_KEY.sub(r"\1=[REDACTED]", s)
    s = _ABS_PATH.sub("[PATH]", s)
    s = _WIN_PATH.sub("[PATH]", s)
    # Generic long secrets last (after specific patterns)
    s = _LONG_SECRET.sub("[REDACTED]", s)
    s = _HEX_SECRET.sub("[REDACTED_HEX]", s)
    s = _BASE64_BLOB.sub("[REDACTED_B64]", s)
    return s.replace("\x00", "")[: max(0, int(max_len))]


def sanitize_for_storage(text: str, *, max_len: int = 500) -> str:
    return sanitize_error(text, max_len=max_len)
