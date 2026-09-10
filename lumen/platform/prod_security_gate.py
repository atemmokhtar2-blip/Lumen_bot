"""Production security gate — Phase A fail-closed (boot + runtime helpers).

Hard rules in production (is_production / non-dev):
  1. Weak operational flags require exact dual-ACK strings (or refuse).
  2. TBE_TOKEN_SECRET, PLATFORM_ADMIN_TOKEN, API_KEY_PEPPER: >=32 + entropy.
  3. Redis must be rediss://; Mongo must use TLS.
  4. LocalProcess is never a production multi-tenant path (see isolation_policy).

Call ``assert_production_security()`` from every process entrypoint before traffic.
Runtime call sites use the ``assert_*_allowed`` helpers so flags cannot be
honored after a process that skipped the boot gate.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger("lumen.prod_security_gate")

# Exact dual-ACK values — must match character-for-character.
ACK_WEAK_PATH = "I_ACCEPT_WEAK_PATH_OPEN"
ACK_SESSION_MEMORY = "I_ACCEPT_SESSION_MEMORY_IN_PROD"
ACK_PUBLIC_BOT = "I_ACCEPT_PUBLIC_ABUSE_RISK"
ACK_CORS_WILD = "I_ACCEPT_CORS_WILDCARD_RISK"
ACK_DOCKER_SOCKET = "I_ACCEPT_DOCKER_SOCKET_RISK"

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


def is_production_runtime() -> bool:
    """True when this process must enforce production hard gates.

    Aligns with secrets_provider: deploy platform markers force production
    even if ENVIRONMENT=dev was left set by mistake.
    """
    try:
        from lumen.platform.secrets_provider import is_production

        return bool(is_production())
    except Exception:
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
        return env not in {"dev", "development", "local", "test"}


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


def _dual_ack_error(flag: str, ack_var: str, ack_value: str) -> str | None:
    """If flag is on without exact ACK, return error string."""
    if not _truthy(flag):
        return None
    if (os.getenv(ack_var) or "").strip() != ack_value:
        return f"{flag} requires {ack_var}={ack_value}"
    return None


# ── Runtime helpers (same rules as boot) ───────────────────────────────────


def assert_weak_path_open_allowed() -> None:
    """Call before honoring TBE_ALLOW_WEAK_PATH_OPEN."""
    if not is_production_runtime():
        return
    err = _dual_ack_error("TBE_ALLOW_WEAK_PATH_OPEN", "TBE_WEAK_PATH_OPEN_ACK", ACK_WEAK_PATH)
    if err:
        raise RuntimeError(err)


def assert_session_memory_allowed() -> None:
    if not is_production_runtime():
        return
    err = _dual_ack_error("SESSION_ALLOW_MEMORY", "SESSION_MEMORY_PROD_ACK", ACK_SESSION_MEMORY)
    if err:
        raise RuntimeError(err)


def assert_public_bot_allowed() -> None:
    if not is_production_runtime():
        return
    err = _dual_ack_error("ALLOW_ALL_USERS", "ALLOW_PUBLIC_BOT_ACK", ACK_PUBLIC_BOT)
    if err:
        raise RuntimeError(err)


def assert_cors_wildcard_allowed() -> None:
    if not is_production_runtime():
        return
    wild = _truthy("API_CORS_ALLOW_WILDCARD") or (os.getenv("API_CORS_ORIGIN") or "").strip() == "*"
    if not wild:
        return
    if (os.getenv("API_CORS_WILDCARD_ACK") or "").strip() != ACK_CORS_WILD:
        raise RuntimeError(
            f"CORS wildcard requires API_CORS_WILDCARD_ACK={ACK_CORS_WILD}"
        )


def assert_docker_socket_allowed() -> None:
    if not is_production_runtime():
        return
    err = _dual_ack_error("TBE_ALLOW_DOCKER_SOCKET", "TBE_DOCKER_SOCKET_ACK", ACK_DOCKER_SOCKET)
    if err:
        raise RuntimeError(err)


def assert_redis_url_tls(url: str) -> None:
    if not is_production_runtime():
        return
    raw = (url or "").strip()
    if not raw:
        raise RuntimeError("REDIS_URL / JOB_REDIS_URL required in production")
    lower = raw.lower()
    if lower.startswith("rediss://"):
        return
    raise RuntimeError(
        "Production Redis must use rediss:// (TLS). Plain redis:// is refused."
    )


def assert_mongo_uri_tls(uri: str) -> None:
    if not is_production_runtime():
        return
    raw = (uri or "").strip()
    if not raw:
        return
    lower = raw.lower()
    if lower.startswith("mongodb+srv://"):
        return
    if any(x in lower for x in ("tls=true", "ssl=true", "tls=1", "ssl=1")):
        return
    raise RuntimeError(
        "Production MongoDB URI must use TLS "
        "(mongodb+srv:// or mongodb://...?tls=true)."
    )


def enforce_redis_url_or_raise(url: str) -> str:
    assert_redis_url_tls(url)
    return url


def enforce_mongo_uri_or_raise(uri: str) -> str:
    assert_mongo_uri_tls(uri)
    return uri


def assert_production_security() -> None:
    """Boot gate — raise RuntimeError if production would run insecurely."""
    if not is_production_runtime():
        logger.info("production security gate skipped (non-production runtime)")
        return

    errors: list[str] = []

    for name in ("TBE_TOKEN_SECRET", "PLATFORM_ADMIN_TOKEN", "API_KEY_PEPPER"):
        err = _secret_ok(name, min_len=32)
        if err:
            errors.append(err)

    bot_tok = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not _truthy("LUMEN_API_ONLY") and (not bot_tok or len(bot_tok) < 20):
        errors.append("TELEGRAM_BOT_TOKEN missing or too short")

    # Phase A dual-ACK flags
    for flag, ack_var, ack_val in (
        ("TBE_ALLOW_WEAK_PATH_OPEN", "TBE_WEAK_PATH_OPEN_ACK", ACK_WEAK_PATH),
        ("SESSION_ALLOW_MEMORY", "SESSION_MEMORY_PROD_ACK", ACK_SESSION_MEMORY),
        ("ALLOW_ALL_USERS", "ALLOW_PUBLIC_BOT_ACK", ACK_PUBLIC_BOT),
        ("TBE_ALLOW_DOCKER_SOCKET", "TBE_DOCKER_SOCKET_ACK", ACK_DOCKER_SOCKET),
    ):
        err = _dual_ack_error(flag, ack_var, ack_val)
        if err:
            errors.append(err)

    try:
        assert_cors_wildcard_allowed()
    except RuntimeError as exc:
        errors.append(str(exc))

    # Absolute: host LocalProcess escapes — no ACK in production
    for flag in (
        "TBE_ALLOW_LOCAL_PROCESS",
        "TBE_FORCE_LOCAL_PROCESS",
        "TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER",
    ):
        if _truthy(flag):
            errors.append(f"{flag} forbidden in production (no bypass)")

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

    # Phase B: PAT in production requires dual-ACK
    if _truthy("GITHUB_ALLOW_PAT"):
        if (os.getenv("GITHUB_ALLOW_PAT_ACK") or "").strip() != "I_ACCEPT_USER_PAT_IN_PROD":
            errors.append(
                "GITHUB_ALLOW_PAT requires GITHUB_ALLOW_PAT_ACK=I_ACCEPT_USER_PAT_IN_PROD"
            )

    if errors:
        msg = "production security gate failed: " + "; ".join(errors)
        logger.error(msg)
        raise RuntimeError(msg)

    try:
        from lumen.platform.secret_rotation import assert_rotation_policy

        assert_rotation_policy()
    except RuntimeError:
        raise
    except Exception:
        logger.exception("secret rotation policy check failed")

    logger.info("production security gate passed (phase A+B)")


__all__ = [
    "assert_production_security",
    "assert_redis_url_tls",
    "assert_mongo_uri_tls",
    "enforce_redis_url_or_raise",
    "enforce_mongo_uri_or_raise",
    "assert_weak_path_open_allowed",
    "assert_session_memory_allowed",
    "assert_public_bot_allowed",
    "assert_cors_wildcard_allowed",
    "assert_docker_socket_allowed",
    "is_production_runtime",
]
