"""Operational security alerts (Phase E) — real delivery paths.

Channels:
  1) SECURITY_ALERT_WEBHOOK_URL — HTTPS JSON POST
  2) SECURITY_ALERT_TELEGRAM_CHAT_ID + bot token
  3) Redis list lumen:security:alerts (always when REDIS_URL set)
  4) Structured log (always for watched events)

Production: at least one external channel OR dual-ACK log-only mode is required
(asserted at boot via prod_security_gate).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger("lumen.platform.security_alerts")

WATCHED_EVENTS = frozenset(
    {
        "auth.admin_rejected",
        "auth.admin_token_unset",
        "auth.admin_rate_limit_unavailable",
        "idor.identity_spoof",
        "webhook.signature_failed",
        "webhook.stripe_signature_failed",
        "webhook.github_signature_failed",
        "edge_waf_rejected",
    }
)

ACK_LOG_ONLY = "I_ACCEPT_SECURITY_ALERTS_LOG_ONLY"

_last_sent: dict[str, float] = {}
_lock = threading.Lock()
_RECENT: list[dict[str, Any]] = []  # ring buffer for tests / local ops
_RECENT_MAX = 200


from lumen.platform.envutil import env_flag as _truthy


def should_alert(event_type: str, severity: str) -> bool:
    et = (event_type or "").strip()
    if et in WATCHED_EVENTS:
        return True
    return (severity or "").lower() == "critical"


def _cooldown_sec() -> float:
    try:
        return max(1.0, float(os.getenv("SECURITY_ALERT_COOLDOWN_SEC") or "30"))
    except ValueError:
        return 30.0


def _allow_send(key: str) -> bool:
    now = time.time()
    cd = _cooldown_sec()
    with _lock:
        last = _last_sent.get(key, 0.0)
        if now - last < cd:
            return False
        _last_sent[key] = now
        if len(_last_sent) > 5000:
            cutoff = now - 3600
            for k in [x for x, t in _last_sent.items() if t < cutoff]:
                del _last_sent[k]
        return True


def _push_recent(payload: dict[str, Any]) -> None:
    with _lock:
        _RECENT.append(payload)
        if len(_RECENT) > _RECENT_MAX:
            del _RECENT[: len(_RECENT) - _RECENT_MAX]


def recent_alerts(*, limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        return list(_RECENT[-max(1, int(limit)) :])


def _redis_feed(payload: dict[str, Any]) -> bool:
    try:
        from lumen.platform.runtime_config import redis_url
        from lumen.platform.redis_client import connect_redis_url

        url = (redis_url() or "").strip()
        if not url:
            return False
        r = connect_redis_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        key = (os.getenv("SECURITY_ALERT_REDIS_KEY") or "lumen:security:alerts").strip()
        r.lpush(key, json.dumps(payload, ensure_ascii=False))
        r.ltrim(key, 0, 999)
        return True
    except Exception:
        logger.debug("security_alert_redis_feed_failed", exc_info=True)
        return False


def _post_webhook(url: str, payload: dict[str, Any]) -> bool:
    try:
        import urllib.request

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Lumen-SecurityAlert/1"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= int(getattr(resp, "status", 200) or 200) < 300
    except Exception as exc:
        logger.warning("security_alert_webhook_failed: %s", type(exc).__name__)
        return False


def _telegram(text: str) -> bool:
    token = (
        (os.getenv("SECURITY_ALERT_TELEGRAM_BOT_TOKEN") or "").strip()
        or (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    )
    chat = (os.getenv("SECURITY_ALERT_TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        return False
    try:
        import urllib.parse
        import urllib.request

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = urllib.parse.urlencode(
            {"chat_id": chat, "text": text[:3500], "disable_web_page_preview": "1"}
        ).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= int(getattr(resp, "status", 200) or 200) < 300
    except Exception as exc:
        logger.warning("security_alert_telegram_failed: %s", type(exc).__name__)
        return False


def has_external_channel() -> bool:
    if (os.getenv("SECURITY_ALERT_WEBHOOK_URL") or "").strip():
        return True
    if (os.getenv("SECURITY_ALERT_TELEGRAM_CHAT_ID") or "").strip():
        return True
    return False


def log_only_mode_allowed() -> bool:
    if _truthy("SECURITY_ALERT_LOG_ONLY", "0"):
        return (os.getenv("SECURITY_ALERT_LOG_ONLY_ACK") or "").strip() == ACK_LOG_ONLY or not _is_prod()
    return False


def _is_prod() -> bool:
    try:
        from lumen.platform.prod_security_gate import is_production_runtime
        return bool(is_production_runtime())
    except Exception:
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        return env not in {"dev", "development", "local", "test"}


def dispatch_alert(
    event_type: str,
    *,
    severity: str = "critical",
    ip: str = "",
    path: str = "",
    tenant_id: str = "",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"sent": False, "channels": []}
    try:
        if not should_alert(event_type, severity):
            return result

        payload = {
            "source": "lumen",
            "event_type": event_type,
            "severity": severity,
            "ip": (ip or "")[:80],
            "path": (path or "")[:300],
            "tenant_id": (tenant_id or "")[:120],
            "detail": {k: str(v)[:200] for k, v in dict(detail or {}).items()},
            "ts": time.time(),
        }
        _push_recent(payload)

        key = f"{event_type}|{ip}|{path}"
        if not _allow_send(key):
            result["deduped"] = True
            result["channels"].append("deduped")
            return result

        text = (
            f"Lumen security alert\n"
            f"type: {event_type}\n"
            f"severity: {severity}\n"
            f"ip: {ip or '-'}\n"
            f"path: {path or '-'}\n"
            f"tenant: {tenant_id or '-'}"
        )

        if _redis_feed(payload):
            result["channels"].append("redis")
            result["sent"] = True

        if _truthy("SECURITY_ALERT_LOG_ONLY", "0") and log_only_mode_allowed():
            logger.critical("SECURITY_ALERT %s", json.dumps(payload, ensure_ascii=False))
            result["channels"].append("log")
            result["sent"] = True
            return result

        wh = (os.getenv("SECURITY_ALERT_WEBHOOK_URL") or "").strip()
        if wh and _post_webhook(wh, payload):
            result["channels"].append("webhook")
            result["sent"] = True

        if _telegram(text):
            result["channels"].append("telegram")
            result["sent"] = True

        # Always structured log for watched events
        logger.critical(
            "SECURITY_ALERT type=%s severity=%s ip=%s path=%s channels=%s",
            event_type,
            severity,
            ip,
            path,
            ",".join(result["channels"]) or "log_only",
        )
        if not result["channels"]:
            result["channels"].append("log")
            result["sent"] = True
    except Exception:
        logger.exception("dispatch_alert_failed type=%s", event_type)
    return result


__all__ = [
    "dispatch_alert",
    "should_alert",
    "WATCHED_EVENTS",
    "recent_alerts",
    "has_external_channel",
    "log_only_mode_allowed",
    "ACK_LOG_ONLY",
]
