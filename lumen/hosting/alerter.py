"""Host plane alerts — notify ops / user when an instance fails health checks.

Channels (any configured):
  TBE_ALERT_TELEGRAM_BOT_TOKEN + TBE_ALERT_TELEGRAM_CHAT_ID
  TBE_ALERT_WEBHOOK_URL  (POST JSON)
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Any

logger = logging.getLogger("tbe.hosting.alerter")

_last_sent: dict[str, float] = {}


def _cooldown_sec() -> float:
    try:
        return max(60.0, float(os.environ.get("TBE_ALERT_COOLDOWN_SEC") or "300"))
    except Exception:
        return 300.0


def _should_send(key: str) -> bool:
    now = time.time()
    last = _last_sent.get(key, 0.0)
    if now - last < _cooldown_sec():
        return False
    _last_sent[key] = now
    return True


def _post_json(url: str, payload: dict[str, Any]) -> bool:
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "Lumen-Host/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception as exc:
        logger.warning("alert webhook failed: %s", type(exc).__name__)
        return False


def _telegram(text: str) -> bool:
    token = (os.environ.get("TBE_ALERT_TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TBE_ALERT_TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _post_json(url, {"chat_id": chat, "text": text[:3500]})


def _email(subject: str, body: str) -> bool:
    host = (os.environ.get("TBE_ALERT_SMTP_HOST") or "").strip()
    to_addr = (os.environ.get("TBE_ALERT_EMAIL_TO") or "").strip()
    if not host or not to_addr:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText

        port = int(os.environ.get("TBE_ALERT_SMTP_PORT") or "587")
        user = (os.environ.get("TBE_ALERT_SMTP_USER") or "").strip()
        password = (os.environ.get("TBE_ALERT_SMTP_PASSWORD") or "").strip()
        from_addr = (os.environ.get("TBE_ALERT_EMAIL_FROM") or user or "alerts@lumen.local").strip()
        msg = MIMEText(body[:8000], "plain", "utf-8")
        msg["Subject"] = subject[:200]
        msg["From"] = from_addr
        msg["To"] = to_addr
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.ehlo()
            if (os.environ.get("TBE_ALERT_SMTP_TLS") or "1").strip() not in {"0", "false"}:
                try:
                    s.starttls()
                except Exception:
                    pass
            if user and password:
                s.login(user, password)
            s.sendmail(from_addr, [to_addr], msg.as_string())
        return True
    except Exception as exc:
        logger.warning("alert email failed: %s", type(exc).__name__)
        return False


def alert_resource(
    *,
    instance_id: str,
    user_id: int,
    metric: str,
    value: float,
    threshold: float,
) -> dict[str, Any]:
    return alert_instance_failed(
        instance_id=instance_id,
        user_id=user_id,
        reason=f"resource:{metric}={value}>{threshold}",
        extra={"metric": metric, "value": value, "threshold": threshold},
    )


def alert_instance_failed(

    *,
    instance_id: str,
    user_id: int,
    reason: str,
    deployment_id: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = f"fail:{instance_id}:{reason[:40]}"
    if not _should_send(key):
        return {"sent": False, "reason": "cooldown"}
    msg = (
        f"[Lumen Host] instance={instance_id} user={user_id} "
        f"dep={deployment_id} FAILED: {reason}"
    )[:3500]
    results = {"telegram": False, "webhook": False, "email": False, "sent": False}
    results["telegram"] = _telegram(msg)
    results["email"] = _email("[Lumen Host] instance failed", msg)
    wh = (os.environ.get("TBE_ALERT_WEBHOOK_URL") or "").strip()
    if wh:
        results["webhook"] = _post_json(
            wh,
            {
                "type": "host_instance_failed",
                "instance_id": instance_id,
                "user_id": user_id,
                "deployment_id": deployment_id,
                "reason": reason,
                "extra": extra or {},
                "ts": time.time(),
            },
        )
    results["sent"] = bool(results["telegram"] or results["webhook"] or results["email"])
    if results["sent"]:
        logger.warning("alert sent instance=%s reason=%s", instance_id, reason[:80])
    return results


__all__ = ["alert_instance_failed"]
