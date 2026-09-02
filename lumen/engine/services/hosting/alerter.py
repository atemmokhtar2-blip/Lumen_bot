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
    results = {"telegram": False, "webhook": False, "sent": False}
    results["telegram"] = _telegram(msg)
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
    results["sent"] = bool(results["telegram"] or results["webhook"])
    if results["sent"]:
        logger.warning("alert sent instance=%s reason=%s", instance_id, reason[:80])
    return results


__all__ = ["alert_instance_failed"]
