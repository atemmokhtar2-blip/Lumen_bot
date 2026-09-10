"""Production security gate — refuse to boot with insecure defaults (Phase A).

Call from API and bot entrypoints before accepting traffic.

Fail-closed rules:
  - Weak operational flags blocked (or dual-ACK only where explicitly allowed)
  - Long-lived secrets required with minimum length + basic entropy
  - Redis must be rediss:// (TLS)
  - Mongo must use TLS (mongodb+srv or tls=true)
  - LocalProcess / host fallbacks forbidden
"""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse

logger = logging.getLogger("lumen.prod_security_gate")

# Dual-ACK values — operator must type the exact string (not 1/true).
_ACK_PUBLIC_BOT = "I_ACCEPT_PUBLIC_ABUSE_RISK"
_ACK_WEAK_PATH = "I_ACCEPT_WEAK_PATH_OPEN"
_ACK_DOCKER_SOCKET = "I_ACCEPT_DOCKER_SOCKET_RISK"
_ACK_CORS_WILD = "I_ACCEPT_CORS_WILDCARD_RISK"
_ACK_REDIS_NO_TLS = "I_ACCEPT_REDIS_WITHOUT_TLS"
_ACK_MONGO_NO_TLS = "I_ACCEPT_MONGO_WITHOUT_TLS"
_ACK_SESSION_MEMORY = "I_ACCEPT_SESSION_MEMORY_IN_PROD"

_WEAK_SECRETS = frozenset(
    {
        "change-me",
        "changeme",
        "secret",
        "password",
        "admin",
        "test",
        "dev",
        "pepper",
        "token",
        "123456",
        "tbe-dev-insecure-token-key",
        "lumen_dev_only_pepper_change_me",
    }
)


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_dev() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    return env in {"dev", "development", "local", "test"}


def _secret_ok(name: str, min_len: int = 32) -> str | None:
    """Return error string if secret is missing/weak; else None."""
    val = (os.getenv(name) or "").strip()
    if not val:
        return f"{name} missing"
    if len(val) < min_len:
        return f"{name} too short (min {min_len})"
    if val.lower() in _WEAK_SECRETS:
        return f"{name} is a known-weak placeholder"
    if len(set(val)) < 10:
        return f"{name} entropy too low (need ≥10 distinct characters)"
    # Reject trivial repeated patterns
    if re.fullmatch(r"(.)\1+", val) or re.fullmatch(r"(..)\1+", val):
        return f"{name} looks patterned/repeated"
    return None


def assert_redis_url_tls(url: str, *, allow_ack: bool = True) -> None:
    """Production: Redis URL must use rediss:// (TLS)."""
    raw = (url or "").strip()
    if not raw:
        raise RuntimeError("REDIS_URL / JOB_REDIS_URL required in production")
    lower = raw.lower()
    if lower.startswith("rediss://"):
        return
    if lower.startswith("redis://"):
        if allow_ack and (os.getenv("REDIS_ALLOW_INSECURE") or "").strip() == _ACK_REDIS_NO_TLS:
            logger.critical(
                "REDIS without TLS allowed via REDIS_ALLOW_INSECURE=%s — not recommended",
                _ACK_REDIS_NO_TLS,
            )
            return
        raise RuntimeError(
            "Production Redis must use rediss:// (TLS). "
            f"Or set REDIS_ALLOW_INSECURE={_ACK_REDIS_NO_TLS} (explicit dual-ACK)."
        )
    raise RuntimeError("REDIS_URL must start with rediss:// (or redis:// only with dual-ACK)")


def assert_mongo_uri_tls(uri: str, *, allow_ack: bool = True) -> None:
    """Production: Mongo URI must use TLS (mongodb+srv or tls/ssl query flags)."""
    raw = (uri or "").strip()
    if not raw:
        return  # Mongo optional for some API-only deploys
    lower = raw.lower()
    if lower.startswith("mongodb+srv://"):
        return  # TLS by default per MongoDB Atlas/spec
    # Standard mongodb:// — require tls=true or ssl=true
    if "tls=true" in lower or "ssl=true" in lower or "tls=1" in lower or "ssl=1" in lower:
        return
    if allow_ack and (os.getenv("MONGO_ALLOW_INSECURE") or "").strip() == _ACK_MONGO_NO_TLS:
        logger.critical(
            "Mongo without TLS allowed via MONGO_ALLOW_INSECURE=%s — not recommended",
            _ACK_MONGO_NO_TLS,
        )
        return
    raise RuntimeError(
        "Production MongoDB URI must use TLS "
        "(mongodb+srv:// or mongodb://...?tls=true). "
        f"Or set MONGO_ALLOW_INSECURE={_ACK_MONGO_NO_TLS} (explicit dual-ACK)."
    )


def assert_production_security() -> None:
    """Raise RuntimeError if production would run with known-insecure settings."""
    if _is_dev():
        logger.info("production security gate skipped (dev environment)")
        return

    errors: list[str] = []

    # --- Required long-lived secrets (strong) ---
    for name, min_len in (
        ("TBE_TOKEN_SECRET", 32),
        ("PLATFORM_ADMIN_TOKEN", 32),
        ("API_KEY_PEPPER", 32),
    ):
        err = _secret_ok(name, min_len=min_len)
        if err:
            errors.append(err)

    # Bot token still required for telegram process; API-only may omit with flag
    bot_tok = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    api_only = _truthy("LUMEN_API_ONLY")
    if not api_only:
        if not bot_tok or len(bot_tok) < 20:
            errors.append("TELEGRAM_BOT_TOKEN missing or too short")

    if not (os.getenv("CALLBACK_HMAC_SECRET") or "").strip():
        logger.warning("CALLBACK_HMAC_SECRET unset — ensure TBE_TOKEN_SECRET is strong")

    # --- Forbidden weak flags (dual-ACK only where listed) ---
    if _truthy("TBE_ALLOW_WEAK_PATH_OPEN"):
        if (os.getenv("TBE_WEAK_PATH_OPEN_ACK") or "").strip() != _ACK_WEAK_PATH:
            errors.append(
                f"TBE_ALLOW_WEAK_PATH_OPEN forbidden without TBE_WEAK_PATH_OPEN_ACK={_ACK_WEAK_PATH}"
            )
        else:
            logger.critical("TBE_ALLOW_WEAK_PATH_OPEN enabled with dual-ACK")

    if _truthy("SESSION_ALLOW_MEMORY"):
        if (os.getenv("SESSION_MEMORY_PROD_ACK") or "").strip() != _ACK_SESSION_MEMORY:
            errors.append(
                f"SESSION_ALLOW_MEMORY forbidden in production without "
                f"SESSION_MEMORY_PROD_ACK={_ACK_SESSION_MEMORY}"
            )
        else:
            logger.critical("SESSION_ALLOW_MEMORY enabled with dual-ACK")

    if _truthy("ALLOW_ALL_USERS"):
        if (os.getenv("ALLOW_PUBLIC_BOT_ACK") or "").strip() != _ACK_PUBLIC_BOT:
            errors.append(
                f"ALLOW_ALL_USERS=1 requires ALLOW_PUBLIC_BOT_ACK={_ACK_PUBLIC_BOT}"
            )

    cors_wild = (os.getenv("API_CORS_ALLOW_WILDCARD") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    cors_origin = (os.getenv("API_CORS_ORIGIN") or "").strip()
    if cors_wild or cors_origin == "*":
        if (os.getenv("API_CORS_WILDCARD_ACK") or "").strip() != _ACK_CORS_WILD:
            errors.append(
                f"CORS wildcard forbidden without API_CORS_WILDCARD_ACK={_ACK_CORS_WILD}"
            )
        else:
            logger.critical("CORS wildcard enabled with dual-ACK")

    if _truthy("TBE_ALLOW_DOCKER_SOCKET"):
        if (os.getenv("TBE_DOCKER_SOCKET_ACK") or "").strip() != _ACK_DOCKER_SOCKET:
            errors.append(
                f"TBE_ALLOW_DOCKER_SOCKET forbidden without TBE_DOCKER_SOCKET_ACK={_ACK_DOCKER_SOCKET}"
            )
        else:
            logger.critical("DOCKER socket allowed with dual-ACK")

    # Absolute forbids — no ACK (host execution escape)
    for forbidden in (
        "TBE_ALLOW_LOCAL_PROCESS",
        "TBE_FORCE_LOCAL_PROCESS",
        "TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER",
    ):
        if _truthy(forbidden):
            errors.append(f"{forbidden} forbidden in production")

    if _truthy("TBE_GIT_CLONE_ALLOW_HOST"):
        if (os.getenv("TBE_ALLOW_HOST_GIT_ACK") or "").strip() != "I_ACCEPT_HOST_GIT_RISK":
            errors.append(
                "TBE_GIT_CLONE_ALLOW_HOST requires TBE_ALLOW_HOST_GIT_ACK=I_ACCEPT_HOST_GIT_RISK"
            )

    if _truthy("CLINE_ALLOW_SHELL"):
        if (os.getenv("CLINE_SHELL_PROD_ACK") or "").strip() != "I_ACCEPT_AGENT_SHELL_RISK":
            errors.append(
                "CLINE_ALLOW_SHELL forbidden without CLINE_SHELL_PROD_ACK=I_ACCEPT_AGENT_SHELL_RISK"
            )

    # --- Data plane TLS ---
    try:
        from lumen.platform.runtime_config import redis_url

        ru = redis_url()
        if ru:
            assert_redis_url_tls(ru)
        else:
            errors.append("REDIS_URL / JOB_REDIS_URL required in production")
    except RuntimeError as exc:
        errors.append(str(exc))
    except Exception as exc:
        errors.append(f"redis_url_check_failed:{type(exc).__name__}")

    mongo_uri = (
        (os.getenv("MONGODB_URI") or "")
        or (os.getenv("MONGO_URL") or "")
        or (os.getenv("MONGODB_URL") or "")
    ).strip()
    if mongo_uri:
        try:
            assert_mongo_uri_tls(mongo_uri)
        except RuntimeError as exc:
            errors.append(str(exc))

    if errors:
        msg = "production security gate failed: " + "; ".join(errors)
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info("production security gate passed (phase A hard gates)")


def enforce_redis_url_or_raise(url: str) -> str:
    """Validate Redis URL at connection time (production TLS)."""
    if _is_dev():
        return url
    assert_redis_url_tls(url)
    return url


def enforce_mongo_uri_or_raise(uri: str) -> str:
    """Validate Mongo URI at connection time (production TLS)."""
    if _is_dev():
        return uri
    assert_mongo_uri_tls(uri)
    return uri


__all__ = [
    "assert_production_security",
    "assert_redis_url_tls",
    "assert_mongo_uri_tls",
    "enforce_redis_url_or_raise",
    "enforce_mongo_uri_or_raise",
]
