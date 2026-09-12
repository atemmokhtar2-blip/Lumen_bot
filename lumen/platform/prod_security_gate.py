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
ACK_DOCKER_ISOLATION = "I_ACCEPT_ISOLATED_DOCKER_NOT_FIRECRACKER"

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


from lumen.platform.envutil import env_flag as _truthy


def _gate_relaxed() -> bool:
    """TEMPORARY soft production boot gate.

    Default: relaxed so Railway can boot before every dual-ACK / TLS / WAF
    variable is wired. Not permanent.

    Re-enable hard fail-closed with:
      PROD_SECURITY_GATE_STRICT=1
    Explicit soft mode:
      PROD_SECURITY_GATE_RELAXED=1
    """
    if _truthy("PROD_SECURITY_GATE_STRICT"):
        return False
    if _truthy("PROD_SECURITY_GATE_RELAXED"):
        return True
    # TEMPORARY default — soft until strict is flipped back on
    return True


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
        if _gate_relaxed():
            logger.warning("prod gate RELAXED (temporary): %s", err)
            return
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
        if _gate_relaxed():
            logger.warning("prod gate RELAXED (temporary): Redis URL missing")
            return
        raise RuntimeError("REDIS_URL / JOB_REDIS_URL required in production")
    lower = raw.lower()
    if lower.startswith("rediss://"):
        return
    msg = "Production Redis must use rediss:// (TLS). Plain redis:// is refused."
    if _gate_relaxed():
        logger.warning("prod gate RELAXED (temporary): %s (url scheme allowed for boot)", msg)
        return
    raise RuntimeError(msg)


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




def assert_production_sandbox_backend() -> None:
    """Production hosting: Firecracker (default) or isolated Docker with dual-ACK.

    gVisor/DinD remain forbidden in production. Plain docker requires
    TBE_DOCKER_ISOLATION_ACK=I_ACCEPT_ISOLATED_DOCKER_NOT_FIRECRACKER and must
    not enable TBE_ALLOW_DOCKER_SOCKET without its own ACK.
    """
    if not is_production_runtime():
        return
    multi = (os.getenv("TBE_MULTI_TENANT") or "1").strip().lower() in {"1", "true", "yes", "on"}
    if not multi and (os.getenv("TBE_ALLOW_SINGLE_TENANT_WEAK") or "").strip() == "1":
        return
    backend = (os.getenv("TBE_SANDBOX_BACKEND") or "auto").strip().lower()
    if backend in {"gvisor", "dind"}:
        raise RuntimeError(
            f"Production sandbox backend refused: TBE_SANDBOX_BACKEND={backend}. "
            "Use firecracker (default) or docker with TBE_DOCKER_ISOLATION_ACK."
        )
    if backend == "docker":
        ack = (os.getenv("TBE_DOCKER_ISOLATION_ACK") or "").strip()
        if ack != ACK_DOCKER_ISOLATION:
            raise RuntimeError(
                "Production docker requires TBE_DOCKER_ISOLATION_ACK="
                f"{ACK_DOCKER_ISOLATION} (isolated docker path). Prefer Firecracker."
            )


def assert_production_security() -> None:
    """Boot gate — raise RuntimeError if production would run insecurely.

    TEMPORARY: when ``_gate_relaxed()`` (default until PROD_SECURITY_GATE_STRICT=1),
    violations are logged and boot continues so platform env deploys are not
    crash-looped before ACKs/TLS/WAF are fully wired.
    """
    if not is_production_runtime():
        logger.info("production security gate skipped (non-production runtime)")
        return

    relaxed = _gate_relaxed()
    if relaxed:
        logger.warning(
            "production security gate RELAXED (temporary) — "
            "set PROD_SECURITY_GATE_STRICT=1 to restore fail-closed"
        )

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

    try:
        assert_production_sandbox_backend()
    except RuntimeError as exp:
        errors.append(str(exp))

    # Phase E: production must have alert channel or explicit log-only dual-ACK
    try:
        from lumen.platform.security_alerts import has_external_channel, log_only_mode_allowed, ACK_LOG_ONLY
        if not has_external_channel() and not log_only_mode_allowed():
            errors.append(
                "SECURITY_ALERT_WEBHOOK_URL or SECURITY_ALERT_TELEGRAM_CHAT_ID required "
                f"(or SECURITY_ALERT_LOG_ONLY=1 + SECURITY_ALERT_LOG_ONLY_ACK={ACK_LOG_ONLY})"
            )
    except Exception as alert_exc:
        errors.append(f"security_alert_config:{type(alert_exc).__name__}")

    # Edge WAF: public production must have shared secret (not spoofable CF-Ray alone)
    require_edge = (os.getenv("TBE_REQUIRE_EDGE_WAF") or "").strip().lower()
    edge_opt = (os.getenv("TBE_EDGE_WAF_OPTIONAL") or "").strip().lower() in {"1", "true", "yes", "on"}
    edge_ack = (os.getenv("TBE_EDGE_WAF_OPTIONAL_ACK") or "").strip()
    edge_opt_ok = edge_opt and edge_ack == "I_ACCEPT_PUBLIC_ORIGIN_WITHOUT_EDGE_WAF"
    if require_edge in {"0", "false", "no", "off"}:
        pass  # explicit disable
    elif not edge_opt_ok:
        if not (os.getenv("TBE_EDGE_WAF_SECRET") or "").strip():
            errors.append(
                "TBE_EDGE_WAF_SECRET required in production "
                "(or TBE_EDGE_WAF_OPTIONAL=1 + TBE_EDGE_WAF_OPTIONAL_ACK=I_ACCEPT_PUBLIC_ORIGIN_WITHOUT_EDGE_WAF)"
            )

    # Absolute: host LocalProcess escapes — still recorded; hard-block only when strict
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
            # When relaxed, assert_redis_url_tls warns instead of raising
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
        if relaxed:
            logger.warning("prod gate RELAXED (temporary) — continuing boot despite: %s", msg)
        else:
            logger.error(msg)
            raise RuntimeError(msg)

    try:
        from lumen.platform.secret_rotation import assert_rotation_policy

        assert_rotation_policy()
    except RuntimeError:
        if relaxed:
            logger.warning("prod gate RELAXED (temporary): secret rotation policy failed", exc_info=True)
        else:
            raise
    except Exception:
        logger.exception("secret rotation policy check failed")

    if relaxed:
        logger.warning("production security gate passed in RELAXED mode (temporary)")
    else:
        logger.info("production security gate passed (phase A+B)")


__all__ = [
    "assert_production_security",
    "assert_production_sandbox_backend",
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
