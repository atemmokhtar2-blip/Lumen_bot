"""Input validation for user-provided configuration values.

Validates bot tokens, bot names, GitHub tokens, and webhook URLs before
they are stored in engine state. Returns clear Arabic error messages so
the user knows exactly what went wrong and how to fix it.

All validators are pure functions (no I/O, no side effects) so they can
be unit-tested without Telegram or network access.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a user input value."""
    ok: bool
    error_ar: str = ""  # Arabic error message (empty when ok=True)


# ---------------------------------------------------------------------------
# Bot token — Telegram format: digits:alphanumeric (35+ chars)
# ---------------------------------------------------------------------------
_BOT_TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")


def validate_bot_token(raw: str) -> ValidationResult:
    """Validate a Telegram bot token from @BotFather.

    Format: <bot_id>:<token_string>
      - bot_id: 6-12 digits
      - token: 30+ alphanumeric chars (incl. _ and -)
    """
    text = re.sub(r"\s+", "", (raw or "").strip())
    if not text:
        return ValidationResult(
            ok=False,
            error_ar="التوكن فارغ. الصق التوكن كاملاً من @BotFather.",
        )
    if ":" not in text:
        return ValidationResult(
            ok=False,
            error_ar="صيغة التوكن غير صحيحة. التوكن يجب أن يحتوي على نقطتين (:) بين رقم البوت والرمز.",
        )
    parts = text.split(":", 1)
    if not parts[0].isdigit():
        return ValidationResult(
            ok=False,
            error_ar="صيغة التوكن غير صحيحة. الجزء قبل النقطتين يجب أن يكون أرقاماً فقط.",
        )
    if not _BOT_TOKEN_RE.match(text):
        return ValidationResult(
            ok=False,
            error_ar="التوكن غير مكتمل أو غير صحيح. تأكد من نسخ التوكن كاملاً من @BotFather (يفضل نسخه ولصقه بدلاً من كتابته يدوياً).",
        )
    return ValidationResult(ok=True)


# ---------------------------------------------------------------------------
# Bot name — Telegram username format
# ---------------------------------------------------------------------------
_BOT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,63}$")


def validate_bot_name(raw: str) -> ValidationResult:
    """Validate a Telegram bot username.

    Rules (Telegram API):
      - 3-64 characters
      - Letters, digits, underscores only (no spaces, no Arabic)
      - Must start with a letter
      - Usually ends with 'bot' but we don't enforce that (user choice)
    """
    text = (raw or "").strip().lstrip("@")
    if not text:
        return ValidationResult(
            ok=False,
            error_ar="اسم البوت فارغ. اكتب اسماً للبوت.",
        )
    if len(text) < 3:
        return ValidationResult(
            ok=False,
            error_ar=f"الاسم قصير جداً ({len(text)} حرف). يجب أن يكون 3 أحرف على الأقل.",
        )
    if len(text) > 64:
        return ValidationResult(
            ok=False,
            error_ar=f"الاسم طويل جداً ({len(text)} حرف). يجب ألا يتجاوز 64 حرفاً.",
        )
    if " " in text:
        return ValidationResult(
            ok=False,
            error_ar="الاسم لا يمكن أن يحتوي على مسافات. استخدم حروفاً وأرقام وشرطة سفلية (_).",
        )
    if not _BOT_NAME_RE.match(text):
        if text[0].isdigit():
            return ValidationResult(
                ok=False,
                error_ar="الاسم يجب أن يبدأ بحرف (وليس رقم).",
            )
        return ValidationResult(
            ok=False,
            error_ar="الاسم يحتوي على رموز غير مسموحة. استخدم الحروف الإنجليزية والأرقام والشرطة السفلية (_) فقط.",
        )
    return ValidationResult(ok=True)


# ---------------------------------------------------------------------------
# GitHub token — Personal Access Token
# ---------------------------------------------------------------------------
_GITHUB_TOKEN_RE = re.compile(r"^(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,})$")


def validate_github_token(raw: str) -> ValidationResult:
    """Validate a GitHub Personal Access Token.

    Accepted formats:
      - Classic: ghp_ + 36 alphanumeric chars
      - Fine-grained: github_pat_ + 40+ alphanumeric/underscore chars
    """
    text = re.sub(r"\s+", "", (raw or "").strip())
    if not text:
        return ValidationResult(
            ok=False,
            error_ar="التوكن فارغ. الصق توكن GitHub كاملاً.",
        )
    if not (text.startswith("ghp_") or text.startswith("github_pat_")):
        return ValidationResult(
            ok=False,
            error_ar="صيغة التوكن غير صحيحة. توكن GitHub يبدأ بـ ghp_ أو github_pat_.",
        )
    if not _GITHUB_TOKEN_RE.match(text):
        return ValidationResult(
            ok=False,
            error_ar="التوكن غير مكتمل أو غير صحيح. تأكد من نسخ التوكن كاملاً من GitHub Settings → Developer settings → Personal access tokens.",
        )
    return ValidationResult(ok=True)


# ---------------------------------------------------------------------------
# Webhook URL — HTTPS endpoint
# ---------------------------------------------------------------------------
_WEBHOOK_RE = re.compile(r"^https://[A-Za-z0-9._\-]+(:\d+)?(/[^\s]*)?$")


def validate_webhook_url(raw: str) -> ValidationResult:
    """Validate a webhook URL.

    Rules:
      - Must start with https:// (no http:// for security)
      - Must have a valid hostname
      - Optional port and path
    """
    text = (raw or "").strip()
    if not text:
        return ValidationResult(
            ok=False,
            error_ar="الرابط فارغ. اكتب رابط الـ webhook.",
        )
    if text.startswith("http://"):
        return ValidationResult(
            ok=False,
            error_ar="الرابط يجب أن يبدأ بـ https:// (وليس http://) للأمان.",
        )
    if not text.startswith("https://"):
        return ValidationResult(
            ok=False,
            error_ar="الرابط يجب أن يبدأ بـ https://",
        )
    if not _WEBHOOK_RE.match(text):
        return ValidationResult(
            ok=False,
            error_ar="صيغة الرابط غير صحيحة. مثال صحيح: https://example.com/webhook",
        )
    return ValidationResult(ok=True)


# ---------------------------------------------------------------------------
# Dispatcher — map slot name to validator
# ---------------------------------------------------------------------------
_VALIDATORS: dict[str, callable] = {
    "bot_token": validate_bot_token,
    "bot_name": validate_bot_name,
    "github_token": validate_github_token,
    "webhook_url": validate_webhook_url,
}


def validate_slot(slot: str, value: str) -> ValidationResult:
    """Validate a user input for a given slot name.

    Returns ValidationResult(ok=True) for slots that don't need validation
    (e.g. free-text descriptions, payment method choices, etc.).
    """
    validator = _VALIDATORS.get(slot)
    if validator is None:
        return ValidationResult(ok=True)
    return validator(value)
