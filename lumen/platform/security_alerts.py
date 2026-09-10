"""Dispatch operational alerts for high-signal security events (Phase E).

Wired from ``security_events.emit`` for critical / watched event types.
Channels (any combination):
  SECURITY_ALERT_WEBHOOK_URL  — HTTPS POST JSON (Slack/Discord/generic)
  SECURITY_ALERT_TELEGRAM_CHAT_ID + TELEGRAM_BOT_TOKEN — Telegram DM/group
  SECURITY_ALERT_LOG_ONLY=1 — force log-only even when channels configured

Never includes secrets in payloads.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger("lumen.platform.security_alerts")

# Events that always page on-call when channels are configured
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

_last_sent: dict[str, float] = {}
_lock = threading.Lock()


def _truthy(name: str, default: str = "0") -> bool:
    return (os.getenv(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def _cooldown_sec() -> float:
    try:
        return max(5.0, float(os.getenv("SECURITY_ALERT_COOLDOWN_SEC") or "60"))
    except ValueError:
        return 60.0


def should_alert(event_type: str, severity: str) -> bool:
    et = (event_type or "").strip()
    if et in WATCHED_EVENTS:
        return True
    return (severity or "").lower() == "critical"


def _dedupe_key(event_type: str, ip: str, path: str) -> str:
    return f"{event_type}|{ip}|{path}"


def _allow_send(key: str) -> bool:
    now = time.time()
    cd = _cooldown_sec()
    with _lock:
        last = _last_sent.get(key, 0.0)
        if now - last < cd:
            return False
        _last_sent[key] = now
        # prune
        if len(_last_sent) > 5000:
            cutoff = now - 3600
            for k in list(_last_sent):
                if _last_sent[k] < cutoff:
                    del _last_sent[k]
        return True


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


def dispatch_alert(
    event_type: str,
    *,
    severity: str = "critical",
    ip: str = "",
    path: str = "",
    tenant_id: str = "",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send alert if configured. Always safe to call (never raises to callers)."""
    result = {"sent": False, "channels": []}
    try:
        if not should_alert(event_type, severity):
            return result
        if _truthy("SECURITY_ALERT_LOG_ONLY", "0"):
            logger.critical(
                "SECURITY_ALERT type=%s severity=%s ip=%s path=%s tenant=%s",
                event_type,
                severity,
                ip,
                path,
                tenant_id,
            )
            result["sent"] = True
            result["channels"].append("log")
            return result

        key = _dedupe_key(event_type, ip, path)
        if not _allow_send(key):
            result["deduped"] = True
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
        text = (
            f"🚨 Lumen security alert\n"
            f"type: {event_type}\n"
            f"severity: {severity}\n"
            f"ip: {ip or '-'}\n"
            f"path: {path or '-'}\n"
            f"tenant: {tenant_id or '-'}"
        )

        wh = (os.getenv("SECURITY_ALERT_WEBHOOK_URL") or "").strip()
        if wh:
            if _post_webhook(wh, payload):
                result["channels"].append("webhook")
                result["sent"] = True

        if _telegram(text):
            result["channels"].append("telegram")
            result["sent"] = True

        if not result["channels"]:
            # No channel configured — still log critical for operators
            logger.critical(
                "SECURITY_ALERT (no channel) type=%s severity=%s ip=%s path=%s",
                event_type,
                severity,
                ip,
                path,
            )
            result["channels"].append("log_fallback")
            result["sent"] = True
    except Exception:
        logger.exception("dispatch_alert_failed type=%s", event_type)
    return result


__all__ = ["dispatch_alert", "should_alert", "WATCHED_EVENTS"]
