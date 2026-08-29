"""Production security gate — refuse to boot with insecure defaults.

Call from API and bot entrypoints before accepting traffic.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("lumen.prod_security_gate")


def assert_production_security() -> None:
    """Raise RuntimeError if production would run with known-insecure settings."""
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    if env in {"dev", "development", "local", "test"}:
        return

    errors: list[str] = []

    def _need(name: str, min_len: int = 16) -> None:
        val = (os.getenv(name) or "").strip()
        if not val or len(val) < min_len:
            errors.append(f"{name} missing or too short (min {min_len})")

    _need("TBE_TOKEN_SECRET", 16)
    _need("TELEGRAM_BOT_TOKEN", 20)
    # Callback HMAC can derive from bot token; prefer dedicated secret
    if not (os.getenv("CALLBACK_HMAC_SECRET") or "").strip():
        logger.warning("CALLBACK_HMAC_SECRET unset — deriving from TELEGRAM_BOT_TOKEN")

    admin = (os.getenv("PLATFORM_ADMIN_TOKEN") or "").strip()
    if not admin or len(admin) < 16:
        errors.append("PLATFORM_ADMIN_TOKEN missing or too short")

    pepper = (os.getenv("API_KEY_PEPPER") or "").strip()
    if not pepper or len(pepper) < 16:
        errors.append("API_KEY_PEPPER missing or too short")

    # Public bot without allowlist is high abuse risk for LLM spend
    allow_all = (os.getenv("ALLOW_ALL_USERS") or "").strip().lower() in {"1", "true", "yes", "on"}
    if allow_all and (os.getenv("ALLOW_PUBLIC_BOT_ACK") or "").strip() != "I_ACCEPT_PUBLIC_ABUSE_RISK":
        errors.append(
            "ALLOW_ALL_USERS=1 requires ALLOW_PUBLIC_BOT_ACK=I_ACCEPT_PUBLIC_ABUSE_RISK"
        )

    # Never allow host git clone of untrusted URLs without isolation
    if (os.getenv("TBE_GIT_CLONE_ALLOW_HOST") or "").strip().lower() in {"1", "true", "yes", "on"}:
        if (os.getenv("TBE_ALLOW_HOST_GIT_ACK") or "").strip() != "I_ACCEPT_HOST_GIT_RISK":
            errors.append(
                "TBE_GIT_CLONE_ALLOW_HOST requires TBE_ALLOW_HOST_GIT_ACK=I_ACCEPT_HOST_GIT_RISK"
            )

    if (os.getenv("CLINE_ALLOW_SHELL") or "").strip().lower() in {"1", "true", "yes", "on"}:
        if (os.getenv("CLINE_SHELL_PROD_ACK") or "").strip() != "I_ACCEPT_AGENT_SHELL_RISK":
            errors.append(
                "CLINE_ALLOW_SHELL forbidden in production without CLINE_SHELL_PROD_ACK=I_ACCEPT_AGENT_SHELL_RISK"
            )

    if (os.getenv("TBE_ALLOW_LOCAL_PROCESS") or "").strip().lower() in {"1", "true", "yes", "on"}:
        errors.append("TBE_ALLOW_LOCAL_PROCESS forbidden in production")
    if (os.getenv("TBE_FORCE_LOCAL_PROCESS") or "").strip().lower() in {"1", "true", "yes", "on"}:
        errors.append("TBE_FORCE_LOCAL_PROCESS forbidden in production")
    if (os.getenv("TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER") or "").strip().lower() in {"1", "true", "yes", "on"}:
        errors.append("TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER forbidden in production")

    if errors:
        msg = "production security gate failed: " + "; ".join(errors)
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info("production security gate passed")
