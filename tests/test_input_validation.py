"""Tests for input validation — bot_token, bot_name, github_token, webhook_url.

Verifies that:
  - Valid inputs are accepted (ok=True, no error)
  - Invalid inputs are rejected with clear Arabic error messages
  - Edge cases (empty, whitespace, wrong format) handled gracefully
"""
from __future__ import annotations

import pytest

from lumen.bot.ui.input_validation import (
    ValidationResult,
    validate_bot_name,
    validate_bot_token,
    validate_github_token,
    validate_slot,
    validate_webhook_url,
)


# ---------------------------------------------------------------------------
# Bot token
# ---------------------------------------------------------------------------
class TestBotTokenValidation:
    def test_valid_token_accepted(self):
        r = validate_bot_token("123456789:ABCdefGHIjklMNOpqrsTUVwxyz-1234567890")
        assert r.ok is True
        assert r.error_ar == ""

    def test_valid_token_with_underscore_dash(self):
        r = validate_bot_token("9876543210:AaBbCcDdEeFfGg_Hh-IiJjKkLlMmNnOoPpQqRrSs")
        assert r.ok is True

    def test_empty_rejected(self):
        r = validate_bot_token("")
        assert r.ok is False
        assert "فارغ" in r.error_ar

    def test_whitespace_only_rejected(self):
        r = validate_bot_token("   \n\t  ")
        assert r.ok is False

    def test_no_colon_rejected(self):
        r = validate_bot_token("123456789ABCdefGHIjklMNOpqrsTUVwxyz")
        assert r.ok is False
        assert "نقطتين" in r.error_ar or ":" in r.error_ar

    def test_non_digit_bot_id_rejected(self):
        r = validate_bot_token("abcdef:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
        assert r.ok is False
        assert "أرقام" in r.error_ar

    def test_short_token_rejected(self):
        r = validate_bot_token("123:short")
        assert r.ok is False
        assert "غير مكتمل" in r.error_ar or "غير صحيح" in r.error_ar

    def test_whitespace_collapsed(self):
        r = validate_bot_token("  123456789:ABCdefGHIjklMNOpqrsTUVwxyz-1234567890  \n")
        assert r.ok is True  # whitespace is stripped/collapsed


# ---------------------------------------------------------------------------
# Bot name
# ---------------------------------------------------------------------------
class TestBotNameValidation:
    def test_valid_name_accepted(self):
        r = validate_bot_name("MyWeatherBot")
        assert r.ok is True

    def test_valid_name_with_underscore(self):
        r = validate_bot_name("my_store_bot")
        assert r.ok is True

    def test_valid_name_with_digits(self):
        r = validate_bot_name("Bot123")
        assert r.ok is True

    def test_at_sign_stripped(self):
        r = validate_bot_name("@MyBot")
        assert r.ok is True

    def test_empty_rejected(self):
        r = validate_bot_name("")
        assert r.ok is False
        assert "فارغ" in r.error_ar

    def test_too_short_rejected(self):
        r = validate_bot_name("ab")
        assert r.ok is False
        assert "قصير" in r.error_ar

    def test_too_long_rejected(self):
        r = validate_bot_name("A" * 65)
        assert r.ok is False
        assert "طويل" in r.error_ar

    def test_spaces_rejected(self):
        r = validate_bot_name("My Bot")
        assert r.ok is False
        assert "مسافات" in r.error_ar

    def test_starts_with_digit_rejected(self):
        r = validate_bot_name("123Bot")
        assert r.ok is False
        assert "حرف" in r.error_ar

    def test_arabic_chars_rejected(self):
        r = validate_bot_name("بوتي")
        assert r.ok is False
        # Arabic chars are not in the allowed charset
        assert r.ok is False

    def test_special_chars_rejected(self):
        r = validate_bot_name("My-Bot!")
        assert r.ok is False
        assert "رموز" in r.error_ar or "غير مسموحة" in r.error_ar


# ---------------------------------------------------------------------------
# GitHub token
# ---------------------------------------------------------------------------
class TestGithubTokenValidation:
    def test_valid_classic_token_accepted(self):
        r = validate_github_token("ghp_" + "A" * 36)
        assert r.ok is True

    def test_valid_fine_grained_token_accepted(self):
        r = validate_github_token("github_pat_" + "A" * 40)
        assert r.ok is True

    def test_empty_rejected(self):
        r = validate_github_token("")
        assert r.ok is False
        assert "فارغ" in r.error_ar

    def test_wrong_prefix_rejected(self):
        r = validate_github_token("abc_1234567890")
        assert r.ok is False
        assert "ghp_" in r.error_ar or "github_pat_" in r.error_ar

    def test_short_classic_rejected(self):
        r = validate_github_token("ghp_" + "A" * 20)
        assert r.ok is False
        assert "غير مكتمل" in r.error_ar or "غير صحيح" in r.error_ar

    def test_whitespace_collapsed(self):
        r = validate_github_token("  ghp_" + "A" * 36 + "  \n")
        assert r.ok is True


# ---------------------------------------------------------------------------
# Webhook URL
# ---------------------------------------------------------------------------
class TestWebhookUrlValidation:
    def test_valid_https_accepted(self):
        r = validate_webhook_url("https://example.com/webhook")
        assert r.ok is True

    def test_valid_https_with_port(self):
        r = validate_webhook_url("https://example.com:8443/webhook")
        assert r.ok is True

    def test_valid_https_root(self):
        r = validate_webhook_url("https://example.com")
        assert r.ok is True

    def test_valid_https_subdomain(self):
        r = validate_webhook_url("https://bot.my-domain.io/hook/tg")
        assert r.ok is True

    def test_empty_rejected(self):
        r = validate_webhook_url("")
        assert r.ok is False
        assert "فارغ" in r.error_ar

    def test_http_rejected(self):
        r = validate_webhook_url("http://example.com/webhook")
        assert r.ok is False
        assert "https" in r.error_ar

    def test_no_scheme_rejected(self):
        r = validate_webhook_url("example.com/webhook")
        assert r.ok is False
        assert "https" in r.error_ar

    def test_malformed_rejected(self):
        r = validate_webhook_url("https://")
        assert r.ok is False
        assert "غير صحيح" in r.error_ar


# ---------------------------------------------------------------------------
# Dispatcher: validate_slot
# ---------------------------------------------------------------------------
class TestValidateSlotDispatcher:
    def test_validated_slot_uses_validator(self):
        r = validate_slot("bot_token", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz-1234567890")
        assert r.ok is True

    def test_invalid_validated_slot_returns_error(self):
        r = validate_slot("bot_token", "bad")
        assert r.ok is False
        assert r.error_ar != ""

    def test_unvalidated_slot_passes_through(self):
        # Slots without a validator should always pass (free text, etc.)
        r = validate_slot("bot_description", "بوت متجر ملابس")
        assert r.ok is True

    def test_unknown_slot_passes_through(self):
        r = validate_slot("some_random_slot", "anything")
        assert r.ok is True

    def test_bot_name_via_dispatcher(self):
        r = validate_slot("bot_name", "MyBot")
        assert r.ok is True

    def test_github_token_via_dispatcher(self):
        r = validate_slot("github_token", "ghp_" + "X" * 36)
        assert r.ok is True

    def test_webhook_url_via_dispatcher(self):
        r = validate_slot("webhook_url", "https://example.com/hook")
        assert r.ok is True


# ---------------------------------------------------------------------------
# Arabic error messages quality
# ---------------------------------------------------------------------------
class TestArabicErrorMessages:
    """Verify error messages are in Arabic and actionable."""

    def test_error_messages_are_arabic(self):
        cases = [
            ("bot_token", ""),
            ("bot_name", ""),
            ("github_token", ""),
            ("webhook_url", ""),
        ]
        for slot, val in cases:
            r = validate_slot(slot, val)
            assert not r.ok
            # Arabic text contains Arabic characters
            assert any("\u0600" <= c <= "\u06FF" for c in r.error_ar), \
                f"Error for {slot} is not Arabic: {r.error_ar}"

    def test_error_messages_actionable(self):
        """Error messages should guide the user on how to fix the issue."""
        r = validate_bot_token("bad")
        assert not r.ok
        # Should mention BotFather or how to get a valid token
        assert "BotFather" in r.error_ar or "نسخ" in r.error_ar or "صحيح" in r.error_ar

    def test_error_messages_no_english_only(self):
        """No error message should be English-only."""
        for validator in [validate_bot_token, validate_bot_name, validate_github_token, validate_webhook_url]:
            r = validator("bad_input_that_will_fail_validation_xxx")
            if not r.ok:
                # Must contain at least some Arabic
                assert any("\u0600" <= c <= "\u06FF" for c in r.error_ar), \
                    f"{validator.__name__} error is not Arabic: {r.error_ar}"
