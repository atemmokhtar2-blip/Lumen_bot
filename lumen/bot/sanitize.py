"""Sanitize secrets and paths before user-facing errors or job storage.

Multi-pass redaction: normalize unicode/spacing, apply many secret patterns
repeatedly until stable. Regex alone is imperfect; iteration + broad patterns
close common bypasses (extra spaces, zero-width chars, alternate prefixes).
"""
from __future__ import annotations

import re
import unicodedata

# Telegram bot tokens: 123456:AA...
_TG_TOKEN = re.compile(r"\b\d{6,12}\s*:\s*[A-Za-z0-9_-]{20,}\b")
# GitHub PATs + fine-grained
_GH_TOKEN = re.compile(
    r"\b(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)\s*[A-Za-z0-9_]{10,}\b",
    re.I,
)
# Stripe / sk_ live keys
_STRIPE = re.compile(r"\b(sk_live_|sk_test_|pk_live_|pk_test_|whsec_)\s*[A-Za-z0-9]+", re.I)
# OpenAI / Anthropic / Groq / Gemini style keys
_LLM_KEY = re.compile(
    r"\b(sk-[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z\-_]{20,}|xai-[A-Za-z0-9]{20,})\b"
)
# Google AI Studio / Gemini access tokens (AQ.… form)
_GOOGLE_AQ = re.compile(r"\bAQ\.[A-Za-z0-9_\-]{20,}\b")
# Env-style KEY=value for common secret names (catches exception messages)
_ENV_SECRET = re.compile(
    r"(?i)\b(GEMINI_API_KEY|GOOGLE_API_KEY|GROQ_API_KEY|OPENAI_API_KEY|TELEGRAM_BOT_TOKEN|"
    r"API_KEY_PEPPER|DATABASE_URL|REDIS_URL|CLINE_API_KEY|ANTHROPIC_API_KEY)"
    r"\s*[=:]\s*[^\s'\"]{8,}"
)
# JWT-ish
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
# Generic bearer / api keys (allow spaces around = or :)
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-+=/]{12,}")
_API_KEY = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd|private[_-]?key|"
    r"client[_-]?secret|authorization)\s*[:=]\s*['\"]?([^\s'\",;]{8,})"
)
# Absolute paths that may leak host layout
_ABS_PATH = re.compile(r"(/(?:home|tmp|var|app|usr|opt|root|Users|data)/[^\s:\"']+)")
# Shell-dangerous chars for path validation
_UNSAFE_PATH = re.compile(r"[;|&$`<>\\\n\r\0*(){}\[\]!#]")
# Zero-width / bidi controls often used to evade simple regex
_ZW = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = _ZW.sub("", s)
    # Collapse odd whitespace around separators used in secrets
    s = re.sub(r"([:=])\s+", r"\1", s)
    return s


def sanitize_error(text: str, *, max_len: int = 200) -> str:
    """Redact tokens/secrets/paths from an error string for user or log display."""
    s = _normalize(text)
    # Multi-pass until stable (handles nested / partial matches)
    for _ in range(4):
        prev = s
        s = _TG_TOKEN.sub("[REDACTED_TELEGRAM_TOKEN]", s)
        s = _GH_TOKEN.sub("[REDACTED_GITHUB_TOKEN]", s)
        s = _STRIPE.sub("[REDACTED_STRIPE_KEY]", s)
        s = _LLM_KEY.sub("[REDACTED_LLM_KEY]", s)
        s = _GOOGLE_AQ.sub("[REDACTED_GOOGLE_TOKEN]", s)
        s = _ENV_SECRET.sub(lambda m: m.group(1) + "=[REDACTED]", s)
        s = _JWT.sub("[REDACTED_JWT]", s)
        s = _BEARER.sub(r"\1[REDACTED]", s)
        s = _API_KEY.sub(r"\1=[REDACTED]", s)
        s = _ABS_PATH.sub("[PATH]", s)
        if s == prev:
            break
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
    if any(seg.startswith("-") and len(seg) > 1 for seg in p.replace("\\", "/").split("/")):
        if "--" in p:
            raise ValueError("invalid_path_characters")
    return p


def sanitize_log_text(text: str, *, max_len: int = 4000) -> str:
    """Strip secrets and HTML/JS-looking payloads from logs shown to users/admins."""
    s = sanitize_error(text or "", max_len=max(max_len, 4000))
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", s)
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


__all__ = ["sanitize_error", "sanitize_for_storage", "assert_safe_fs_path", "sanitize_log_text"]


import logging


class SecretRedactFilter(logging.Filter):
    """Apply sanitize_error to every log record msg/args (defense in depth)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = sanitize_error(record.msg, max_len=4000)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: sanitize_error(str(v), max_len=500) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        sanitize_error(str(a), max_len=500) if isinstance(a, str) else a
                        for a in record.args
                    )
            if record.exc_text:
                record.exc_text = sanitize_error(record.exc_text, max_len=4000)
        except Exception:
            pass
        return True


def install_secret_log_filter() -> None:
    """Attach SecretRedactFilter to root and common app loggers once."""
    filt = SecretRedactFilter()
    root = logging.getLogger()
    if not any(isinstance(f, SecretRedactFilter) for f in root.filters):
        root.addFilter(filt)
    for name in (
        "lumen",
        "telegram",
        "lumen.engine",
        "lumen.platform",
        "api",
    ):
        log = logging.getLogger(name)
        if not any(isinstance(f, SecretRedactFilter) for f in log.filters):
            log.addFilter(filt)




def user_facing_generation_error(exc: BaseException | None = None, *, code: str | None = None) -> str:
    """User-visible generation failure — generic codes only; full detail stays in logs.

    Never echo exception messages, paths, or stack fragments to Telegram clients.
    """
    if code:
        c = str(code).strip()[:64] or "generation_failed"
    elif exc is not None:
        name = type(exc).__name__
        if name in {"FileNotFoundError", "NotADirectoryError"}:
            c = "missing_resource"
        elif name in {"PermissionError"}:
            c = "permission_denied"
        elif name in {"TimeoutError", "EngineTimeoutError"}:
            c = "timeout"
        elif name == "RuntimeError" and "sandbox" in str(exc).lower():
            c = "sandbox_unavailable"
        else:
            c = "generation_failed"
    else:
        c = "generation_failed"
    return (
        "❌ تعذر إكمال التوليد."
        + chr(10)
        + f"رمز الخطأ: `{c}`"
        + chr(10)
        + "أعد المحاولة لاحقًا. إذا تكرر الخطأ تواصل مع الدعم مع ذكر الرمز فقط."
    )


__all__ = [
    "sanitize_error",
    "user_facing_generation_error",
    "sanitize_for_storage",
    "assert_safe_fs_path",
    "sanitize_log_text",
    "SecretRedactFilter",
    "install_secret_log_filter",
]
