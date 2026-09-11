"""Phase 6 strong — multi-signal health for lumen_serverless instances.

Signals (fail-closed when available):
  1) Platform deployment status MUST be READY/running
  2) HTTP adapter health JSON on webhook path
  3) Telegram getWebhookInfo URL match (when sealed bot token available)

No vendor strings in user-facing reasons.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("lumen.hosting.serverless_health")


@dataclass
class HealthReport:
    ok: bool
    reason: str = ""
    signals: dict[str, Any] = field(default_factory=dict)
    at: float = field(default_factory=time.time)

    def as_diag(self) -> dict[str, Any]:
        return {
            "last_health_ok": self.ok,
            "last_health_reason": self.reason,
            "last_health_at": self.at,
            "health_signals": dict(self.signals),
        }


def _backend_name(inst) -> str:
    return str(getattr(inst, "sandbox_backend", "") or "").strip().lower()


def is_serverless_instance(inst) -> bool:
    return _backend_name(inst) in {"lumen_serverless", "serverless", "vercel"}


def probe_platform_status(inst) -> tuple[bool, str, dict[str, Any]]:
    dep = str(getattr(inst, "deployment_id", "") or "").strip()
    if not dep:
        return False, "no_deployment_id", {}
    try:
        from lumen.engine.services.live_deployment.vercel_process_driver import VercelProcessDriver

        st = VercelProcessDriver().status(dep)
        status = str(getattr(st, "status", "") or "").lower()
        url = str(getattr(st, "url", "") or "")
        meta = {"platform_status": status, "platform_url": url, "deployment_id": dep}
        if status in {"running", "ready"}:
            return True, "platform_ready", meta
        if status in {"pending", "building"}:
            return False, "platform_pending", meta
        return False, f"platform_{status or 'down'}", meta
    except Exception as exc:
        logger.debug("platform probe failed: %s", type(exc).__name__)
        return False, f"platform_error:{type(exc).__name__}", {"deployment_id": dep}


def probe_http_adapter(inst) -> tuple[bool, str, dict[str, Any]]:
    base = str(getattr(inst, "public_base_url", "") or "").rstrip("/")
    diag = dict(getattr(inst, "last_diagnosis", None) or {})
    path = str(diag.get("webhook_path") or "/api")
    if not path.startswith("/"):
        path = "/" + path
    if not base.startswith("https://"):
        hook = str(getattr(inst, "webhook_public_url", "") or diag.get("webhook_url") or "")
        if hook.startswith("https://"):
            # derive base from webhook URL
            try:
                from urllib.parse import urlparse
                u = urlparse(hook)
                base = f"{u.scheme}://{u.netloc}"
            except Exception:
                base = ""
    if not base.startswith("https://"):
        return False, "no_public_url", {}
    try:
        from lumen.hosting.serverless_verify import health_check_deployment, normalize_public_url

        result = health_check_deployment(
            normalize_public_url(base),
            webhook_path=path,
            retries=2,
            delay_sec=0.4,
            timeout=10.0,
        )
        meta = {
            "http_ok": bool(result.get("ok")),
            "http_error": str(result.get("error") or "")[:120],
            "adapter_ok": bool(result.get("adapter_ok")),
            "token_configured": result.get("token_configured"),
            "healthy_url": result.get("healthy_url") or "",
        }
        if result.get("ok"):
            return True, "http_ok", meta
        return False, str(result.get("error") or "http_unhealthy"), meta
    except Exception as exc:
        return False, f"http_error:{type(exc).__name__}", {}


def _load_sealed_token(inst) -> str:
    path = str(getattr(inst, "project_path", "") or "")
    if not path:
        return ""
    try:
        from lumen.hosting.secrets_env import load_project_secrets
        sealed = load_project_secrets(path)
        return (sealed.get("BOT_TOKEN") or sealed.get("TELEGRAM_BOT_TOKEN") or "").strip()
    except Exception:
        return ""


def probe_telegram_webhook(inst, *, bot_token: str = "") -> tuple[bool, str, dict[str, Any]]:
    token = (bot_token or "").strip() or _load_sealed_token(inst)
    if not token or ":" not in token:
        return True, "telegram_skipped_no_token", {"telegram_checked": False}

    expected = str(getattr(inst, "webhook_public_url", "") or "").strip()
    diag = dict(getattr(inst, "last_diagnosis", None) or {})
    if not expected:
        expected = str(diag.get("webhook_url") or "").strip()
    try:
        from lumen.hosting.serverless_verify import get_webhook_info, normalize_webhook_url, normalize_public_url

        info = get_webhook_info(token)
        actual = str(info.get("url") or "").strip()
        meta = {
            "telegram_checked": True,
            "telegram_url": actual[:200],
            "expected_url": expected[:200],
            "pending_update_count": info.get("pending_update_count"),
            "last_error_message": str(info.get("last_error_message") or "")[:160],
        }
        if not actual:
            return False, "telegram_webhook_empty", meta
        if expected and actual.rstrip("/") != expected.rstrip("/"):
            # also accept path variants
            if expected not in actual and actual not in expected:
                return False, "telegram_webhook_mismatch", meta
        if info.get("last_error_message"):
            # soft: still ok if URL matches but report
            meta["telegram_has_delivery_error"] = True
        return True, "telegram_ok", meta
    except Exception as exc:
        return False, f"telegram_error:{type(exc).__name__}", {"telegram_checked": True}


def evaluate_serverless_instance(inst, *, bot_token: str = "") -> HealthReport:
    signals: dict[str, Any] = {}
    platform_ok, platform_reason, pmeta = probe_platform_status(inst)
    signals["platform"] = {"ok": platform_ok, "reason": platform_reason, **pmeta}

    http_ok, http_reason, hmeta = probe_http_adapter(inst)
    signals["http"] = {"ok": http_ok, "reason": http_reason, **hmeta}

    tg_ok, tg_reason, tmeta = probe_telegram_webhook(inst, bot_token=bot_token)
    signals["telegram"] = {"ok": tg_ok, "reason": tg_reason, **tmeta}

    # Fail-closed: platform + http required; telegram required when checked with token
    failures = []
    if not platform_ok:
        failures.append(platform_reason)
    if not http_ok:
        failures.append(http_reason)
    if tmeta.get("telegram_checked") and not tg_ok:
        failures.append(tg_reason)

    if failures:
        return HealthReport(ok=False, reason="+".join(failures)[:200], signals=signals)
    return HealthReport(ok=True, reason="all_signals_ok", signals=signals)


def collect_serverless_logs(inst, *, limit: int = 80) -> list[str]:
    """Best-effort platform logs; empty list if unavailable."""
    dep = str(getattr(inst, "deployment_id", "") or "").strip()
    lines: list[str] = []
    if dep:
        try:
            from lumen.engine.services.live_deployment.vercel_process_driver import VercelProcessDriver
            driver = VercelProcessDriver()
            if hasattr(driver, "logs"):
                raw = driver.logs(dep, limit=limit)  # type: ignore[attr-defined]
                if isinstance(raw, list):
                    lines = [str(x) for x in raw][-limit:]
                elif isinstance(raw, str):
                    lines = raw.splitlines()[-limit:]
        except Exception:
            logger.debug("serverless logs unavailable", exc_info=True)
    # diagnosis phases as synthetic log
    diag = dict(getattr(inst, "last_diagnosis", None) or {})
    phases = diag.get("phases") or []
    if isinstance(phases, list):
        for p in phases[-10:]:
            if isinstance(p, dict):
                lines.append(
                    f"phase {p.get('state')}: ok={p.get('ok')} {str(p.get('detail') or '')[:80]}"
                )
    signals = diag.get("health_signals") or {}
    if signals:
        lines.append(f"health_signals: {signals}")
    return lines[-limit:]


__all__ = [
    "HealthReport",
    "is_serverless_instance",
    "evaluate_serverless_instance",
    "probe_platform_status",
    "probe_http_adapter",
    "probe_telegram_webhook",
    "collect_serverless_logs",
]
