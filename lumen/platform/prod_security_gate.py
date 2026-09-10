"""Production security gate — refuse to boot with insecure defaults (Phase A).

Strict fail-closed:
  - Listed weak flags: ABSOLUTE refuse in production (no dual-ACK escape)
  - Secrets >=32 chars with entropy checks
  - Redis must be rediss:// (no escape)
  - Mongo must use TLS (no escape)
  - LocalProcess flags absolute refuse
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger("lumen.prod_security_gate")

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

# Phase A flags — absolute refuse in production (no ACK bypass).
_ABSOLUTE_FORBIDDEN_FLAGS = (
    "TBE_ALLOW_WEAK_PATH_OPEN",
    "SESSION_ALLOW_MEMORY",
    "TBE_ALLOW_DOCKER_SOCKET",
    "TBE_ALLOW_LOCAL_PROCESS",
    "TBE_FORCE_LOCAL_PROCESS",
    "TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER",
    "API_CORS_ALLOW_WILDCARD",
)


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_dev() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    return env in {"dev", "development", "local", "test"}


def _secret_ok(name: str, min_len: int = 32) -> str | None:
    val = (os.getenv(name) or "").strip()
    if not val:
        return f"{name} missing"
    if len(val) < min_len:
        return f"{name} too short (min {min_len})"
    if val.lower() in _WEAK_SECRETS:
        return f"{name} is a known-weak placeholder"
    if len(set(val)) < 10:
        return f"{name} entropy too low (need >=10 distinct characters)"
    if re.fullmatch(r"(.)\1+", val) or re.fullmatch(r"(..)\1+", val):
        return f"{name} looks patterned/repeated"
    return None


def assert_redis_url_tls(url: str, *, allow_ack: bool = False) -> None:
    """Production: Redis URL must use rediss:// (TLS). No ACK bypass."""
    raw = (url or "").strip()
    if not raw:
        raise RuntimeError("REDIS_URL / JOB_REDIS_URL required in production")
    lower = raw.lower()
    if lower.startswith("rediss://"):
        return
    if lower.startswith("redis://"):
        raise RuntimeError(
            "Production Redis must use rediss:// (TLS). Plain redis:// is refused."
        )
    raise RuntimeError("REDIS_URL must start with rediss://")


def assert_mongo_uri_tls(uri: str, *, allow_ack: bool = False) -> None:
    """Production: Mongo URI must use TLS. No ACK bypass."""
    raw = (uri or "").strip()
    if not raw:
        return
    lower = raw.lower()
    if lower.startswith("mongodb+srv://"):
        return
    if "tls=true" in lower or "ssl=true" in lower or "tls=1" in lower or "ssl=1" in lower:
        return
    raise RuntimeError(
        "Production MongoDB URI must use TLS "
        "(mongodb+srv:// or mongodb://...?tls=true). Plain mongodb:// refused."
    )


def assert_production_security() -> None:
    """Raise RuntimeError if production would run with known-insecure settings."""
    if _is_dev():
        logger.info("production security gate skipped (dev environment)")
        return

    errors: list[str] = []

    for name, min_len in (
        ("TBE_TOKEN_SECRET", 32),
        ("PLATFORM_ADMIN_TOKEN", 32),
        ("API_KEY_PEPPER", 32),
    ):
        err = _secret_ok(name, min_len=min_len)
        if err:
            errors.append(err)

    bot_tok = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    api_only = _truthy("LUMEN_API_ONLY")
    if not api_only and (not bot_tok or len(bot_tok) < 20):
        errors.append("TELEGRAM_BOT_TOKEN missing or too short")

    for flag in _ABSOLUTE_FORBIDDEN_FLAGS:
        if _truthy(flag):
            errors.append(f"{flag} forbidden in production (no bypass)")

    if (os.getenv("API_CORS_ORIGIN") or "").strip() == "*":
        errors.append("API_CORS_ORIGIN=* forbidden in production (no bypass)")

    if _truthy("ALLOW_ALL_USERS"):
        if (os.getenv("ALLOW_PUBLIC_BOT_ACK") or "").strip() != "I_ACCEPT_PUBLIC_ABUSE_RISK":
            errors.append(
                "ALLOW_ALL_USERS=1 requires ALLOW_PUBLIC_BOT_ACK=I_ACCEPT_PUBLIC_ABUSE_RISK"
            )

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

    try:
        from lumen.platform.runtime_config import redis_url

        ru = redis_url()
        if not ru:
            errors.append("REDIS_URL / JOB_REDIS_URL required in production")
        else:
            assert_redis_url_tls(ru)
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

    logger.info("production security gate passed (phase A strict)")


def enforce_redis_url_or_raise(url: str) -> str:
    if _is_dev():
        return url
    assert_redis_url_tls(url)
    return url


def enforce_mongo_uri_or_raise(uri: str) -> str:
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
