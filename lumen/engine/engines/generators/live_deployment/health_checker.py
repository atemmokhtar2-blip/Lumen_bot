"""
Live Health Check — Specification 065.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

from .report_data import HealthCheckResult
from .secrets_manager import SecretsManager

_log = logging.getLogger("engine.live_deployment.health")


class HealthChecker:
    """Verify the bot is reachable via Telegram getMe / getWebhookInfo."""

    def check(self, secrets: SecretsManager, secret_id: str) -> HealthCheckResult:
        result = HealthCheckResult()
        token = secrets.get(secret_id)
        if not token:
            result.details = "No token available for health check."
            return result

        t0 = time.perf_counter()
        try:
            me = self._api(token, "getMe")
            result.latency_ms = (time.perf_counter() - t0) * 1000.0
            if not me.get("ok"):
                result.details = "getMe returned not ok."
                return result
            result.online = True
            result.telegram_reachable = True

            # Polling vs webhook
            try:
                wh = self._api(token, "getWebhookInfo")
                if wh.get("ok"):
                    info = wh.get("result") or {}
                    url = str(info.get("url") or "")
                    if url:
                        result.polling_or_webhook_ok = True
                        result.details = f"Webhook configured: {url[:60]}"
                    else:
                        # No webhook → polling mode is expected for simple bots
                        result.polling_or_webhook_ok = True
                        result.details = "No webhook set (polling mode expected)."
            except Exception:
                result.polling_or_webhook_ok = result.online
                result.details = "getWebhookInfo unavailable; getMe succeeded."

            _log.info(
                "Health check complete",
                extra={
                    "online": result.online,
                    "latency_ms": round(result.latency_ms, 1),
                },
            )
            return result
        except Exception as e:
            result.details = f"Health check failed: {type(e).__name__}"
            result.latency_ms = (time.perf_counter() - t0) * 1000.0
            return result

    @staticmethod
    def _api(token: str, method: str) -> dict:
        import os
        import time
        import urllib.error
        import urllib.request

        try:
            timeout = max(8.0, min(float(os.environ.get("TELEGRAM_API_TIMEOUT", "30") or "30"), 90.0))
        except ValueError:
            timeout = 30.0
        url = f"https://api.telegram.org/bot{token}/{method}"
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                req = urllib.request.Request(
                    url,
                    method="GET",
                    headers={"User-Agent": "Lumen-LiveDeploy/1.0"},
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                last_exc = e
                if attempt < 3:
                    time.sleep(float(attempt))
        if last_exc:
            raise last_exc
        return {}
