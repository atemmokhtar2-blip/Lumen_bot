"""Sanitize secrets and paths before user-facing errors or job storage."""
from __future__ import annotations

import re

# Telegram bot tokens: 123456:AA... (BotFather uses 6–12 digit ids)
_TG_TOKEN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
# GitHub PATs + fine-grained
_GH_TOKEN = re.compile(
    r"\b(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{10,}\b"
)
# Stripe / sk_ live keys
_STRIPE = re.compile(r"\b(sk_live_|sk_test_|pk_live_|pk_test_|whsec_)[A-Za-z0-9]+")
# Generic bearer / api keys
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{12,}")
_API_KEY = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([^\s'\"]{8,})"
)
# Absolute paths that may leak host layout
_ABS_PATH = re.compile(r"(/(?:home|tmp|var|app|usr|opt|root)/[^\s:\"']+)")
# Shell-dangerous chars for path validation (incl. command substitution)
_UNSAFE_PATH = re.compile(r"[;|&$`<>\\\n\r\0*(){}\[\]!#]")


def sanitize_error(text: str, *, max_len: int = 200) -> str:
    """Redact tokens/secrets/paths from an error string for user or log display."""
    s = str(text or "")
    s = _TG_TOKEN.sub("[REDACTED_TELEGRAM_TOKEN]", s)
    s = _GH_TOKEN.sub("[REDACTED_GITHUB_TOKEN]", s)
    s = _STRIPE.sub("[REDACTED_STRIPE_KEY]", s)
    s = _BEARER.sub(r"\1[REDACTED]", s)
    s = _API_KEY.sub(r"\1=[REDACTED]", s)
    s = _ABS_PATH.sub("[PATH]", s)
    s = s.replace("\x00", "")
    return s[: max(0, int(max_len))]


def sanitize_for_storage(text: str, *, max_len: int = 500) -> str:
    """Stricter sanitization for persisted job/API errors (no raw paths/tokens)."""
    return sanitize_error(text, max_len=max_len)


def assert_safe_fs_path(path: str) -> str:
    """Reject paths with shell metacharacters. Does not allow command injection via path."""
    p = str(path or "").strip()
    if not p:
        raise ValueError("empty_path")
    if _UNSAFE_PATH.search(p):
        raise ValueError("invalid_path_characters")
    if "\n" in p or "\r" in p or "\x00" in p:
        raise ValueError("invalid_path_characters")
    # Reject path segments that look like shell expansion
    if any(seg.startswith("-") and len(seg) > 1 for seg in p.replace("\\", "/").split("/")):
        # allow relative "./x" but not "--flag"
        if "--" in p:
            raise ValueError("invalid_path_characters")
    return p


__all__ = ["sanitize_error", "sanitize_for_storage", "assert_safe_fs_path", "sanitize_log_text"]


def sanitize_log_text(text: str, *, max_len: int = 4000) -> str:
    """Strip secrets and HTML/JS-looking payloads from logs shown to users/admins."""
    import re
    s = (text or "")
    # Redact token-like and key-like values
    s = re.sub(r"(?i)(bot[_-]?token|api[_-]?key|secret|password|authorization)\s*[:=]\s*\S+", r"\1=[REDACTED]", s)
    s = re.sub(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b", "[REDACTED_BOT_TOKEN]", s)
    s = re.sub(r"\b(sk_live_|sk_test_|ghp_|github_pat_|glpat-)[A-Za-z0-9_-]+", "[REDACTED_SECRET]", s)
    # Neutralize HTML/script for admin UI
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", s)
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s
