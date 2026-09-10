"""Secret rotation policy (Phase B).

Tracks last-rotation timestamps for long-lived platform secrets and enforces
a maximum age at boot. Operators record a rotation after changing a secret in
the Secret Manager / platform variables.

Redis keys: lumen:secret_rotation:{name} → unix ts (string)
Env overrides:
  SECRET_ROTATION_MAX_DAYS   default 90
  SECRET_ROTATION_FAIL_CLOSED  if 1, boot fails when overdue (else critical log)
  SECRET_ROTATION_NAMES      comma list (default core set)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Iterable

logger = logging.getLogger("lumen.secret_rotation")

_PREFIX = "lumen:secret_rotation:"
_DEFAULT_NAMES = (
    "PLATFORM_ADMIN_TOKEN",
    "API_KEY_PEPPER",
    "TBE_TOKEN_SECRET",
    "STRIPE_WEBHOOK_SECRET",
    "GITHUB_WEBHOOK_SECRET",
    "CALLBACK_HMAC_SECRET",
)


def _max_age_sec() -> float:
    days = float(os.getenv("SECRET_ROTATION_MAX_DAYS") or "90")
    return max(1.0, days) * 86400.0


def _names() -> list[str]:
    raw = (os.getenv("SECRET_ROTATION_NAMES") or "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return list(_DEFAULT_NAMES)


def _redis():
    try:
        from lumen.platform.redis_client import connect_redis_url
        from lumen.platform.runtime_config import redis_url

        url = (redis_url() or "").strip()
        if not url:
            return None
        return connect_redis_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
    except Exception:
        logger.debug("secret_rotation redis unavailable", exc_info=True)
        return None


def record_rotation(name: str, *, when: float | None = None) -> bool:
    """Mark ``name`` as rotated now (call after secret is replaced in SM)."""
    key = f"{_PREFIX}{name.strip()}"
    ts = str(int(when if when is not None else time.time()))
    r = _redis()
    if r is None:
        logger.warning("record_rotation skipped (no redis) name=%s", name)
        return False
    try:
        r.set(key, ts)
        logger.info("secret_rotation recorded name=%s", name)
        return True
    except Exception:
        logger.exception("record_rotation failed name=%s", name)
        return False


def last_rotation_ts(name: str) -> float | None:
    r = _redis()
    if r is None:
        return None
    try:
        raw = r.get(f"{_PREFIX}{name.strip()}")
        if raw is None:
            return None
        return float(raw)
    except Exception:
        return None


def rotation_status(names: Iterable[str] | None = None) -> list[dict]:
    """Return status rows for operators / admin diagnostics."""
    now = time.time()
    max_age = _max_age_sec()
    out: list[dict] = []
    for name in names or _names():
        ts = last_rotation_ts(name)
        age = (now - ts) if ts is not None else None
        out.append(
            {
                "name": name,
                "last_rotation_ts": ts,
                "age_sec": age,
                "max_age_sec": max_age,
                "overdue": age is not None and age > max_age,
                "never_recorded": ts is None,
            }
        )
    return out


def assert_rotation_policy(*, fail_closed: bool | None = None) -> None:
    """Boot check: log overdue secrets; optionally refuse start.

    First boot (never_recorded): records baseline timestamps so operators get a
    90-day window from deploy, not an immediate fail.
    """
    try:
        from lumen.platform.prod_security_gate import is_production_runtime

        if not is_production_runtime():
            return
    except Exception:
        env = (os.getenv("ENVIRONMENT") or "").strip().lower()
        if env in {"dev", "development", "local", "test"}:
            return

    if fail_closed is None:
        fail_closed = (os.getenv("SECRET_ROTATION_FAIL_CLOSED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    rows = rotation_status()
    overdue: list[str] = []
    for row in rows:
        name = row["name"]
        if row["never_recorded"]:
            # Baseline: mark as rotated at boot so policy starts from now
            record_rotation(name)
            logger.info("secret_rotation baseline recorded name=%s", name)
            continue
        if row["overdue"]:
            overdue.append(name)
            logger.critical(
                "secret_rotation overdue name=%s age_sec=%s max=%s",
                name,
                int(row["age_sec"] or 0),
                int(row["max_age_sec"]),
            )

    if overdue and fail_closed:
        raise RuntimeError(
            "secret rotation overdue (set SECRET_ROTATION_FAIL_CLOSED=0 to warn-only): "
            + ", ".join(overdue)
        )


def pat_allowed_in_production() -> bool:
    """True when operator explicitly allows user PAT path in production."""
    if (os.getenv("GITHUB_ALLOW_PAT") or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False
    return (os.getenv("GITHUB_ALLOW_PAT_ACK") or "").strip() == "I_ACCEPT_USER_PAT_IN_PROD"


__all__ = [
    "record_rotation",
    "last_rotation_ts",
    "rotation_status",
    "assert_rotation_policy",
    "pat_allowed_in_production",
]
