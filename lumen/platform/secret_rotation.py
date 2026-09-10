"""Secret rotation policy (Phase B) — operator-driven, not theater.

Timestamps are recorded ONLY when:
  - Admin calls POST /v1/admin/secret-rotation, or
  - record_rotation() is invoked after a real secret change, or
  - SECRET_ROTATION_BOOTSTRAP_ACK=I_ACCEPT_ROTATION_BASELINE at first boot
    (explicit one-time baseline, not silent health fake).

Boot policy:
  - never_recorded → critical log; fail if SECRET_ROTATION_FAIL_CLOSED=1
  - overdue (age > SECRET_ROTATION_MAX_DAYS, default 90) → same
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
_BOOTSTRAP_ACK = "I_ACCEPT_ROTATION_BASELINE"
_PAT_ACK = "I_ACCEPT_USER_PAT_IN_PROD"


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
        return connect_redis_url(
            url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
    except Exception:
        logger.debug("secret_rotation redis unavailable", exc_info=True)
        return None


def record_rotation(name: str, *, when: float | None = None) -> bool:
    """Mark secret as rotated — call only after the value changed in Secret Manager."""
    key = f"{_PREFIX}{name.strip()}"
    ts = str(int(when if when is not None else time.time()))
    r = _redis()
    if r is None:
        logger.warning("record_rotation skipped (no redis) name=%s", name)
        return False
    try:
        r.set(key, ts)
        logger.info("secret_rotation recorded name=%s ts=%s", name, ts)
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
                "overdue": bool(age is not None and age > max_age),
                "never_recorded": ts is None,
            }
        )
    return out


def assert_rotation_policy(*, fail_closed: bool | None = None) -> None:
    """Boot check — does NOT silently baseline (that was hollow)."""
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
            "1", "true", "yes", "on",
        }

    bootstrap = (os.getenv("SECRET_ROTATION_BOOTSTRAP_ACK") or "").strip() == _BOOTSTRAP_ACK
    rows = rotation_status()
    problems: list[str] = []

    for row in rows:
        name = row["name"]
        if row["never_recorded"]:
            if bootstrap:
                record_rotation(name)
                logger.warning(
                    "secret_rotation BOOTSTRAP baseline name=%s "
                    "(remove SECRET_ROTATION_BOOTSTRAP_ACK after first deploy)",
                    name,
                )
                continue
            problems.append(f"{name}:never_recorded")
            logger.critical(
                "secret_rotation never recorded for %s — "
                "POST /v1/admin/secret-rotation after rotating in Secret Manager "
                "or set SECRET_ROTATION_BOOTSTRAP_ACK=%s once",
                name,
                _BOOTSTRAP_ACK,
            )
        elif row["overdue"]:
            problems.append(f"{name}:overdue_age={int(row['age_sec'] or 0)}")
            logger.critical(
                "secret_rotation overdue name=%s age_sec=%s max=%s",
                name,
                int(row["age_sec"] or 0),
                int(row["max_age_sec"]),
            )

    if problems and fail_closed:
        raise RuntimeError(
            "secret rotation policy failed: " + ", ".join(problems)
        )


def pat_allowed_in_production() -> bool:
    if (os.getenv("GITHUB_ALLOW_PAT") or "").strip().lower() not in {
        "1", "true", "yes", "on",
    }:
        return False
    return (os.getenv("GITHUB_ALLOW_PAT_ACK") or "").strip() == _PAT_ACK


__all__ = [
    "record_rotation",
    "last_rotation_ts",
    "rotation_status",
    "assert_rotation_policy",
    "pat_allowed_in_production",
]
