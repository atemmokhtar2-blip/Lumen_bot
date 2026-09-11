"""Periodic health checks for PERMANENT_HOST + lumen_serverless instances.

Every ~30s (configurable):
  1) Lists running HostInstance records
  2) Probes backend (Firecracker status OR serverless HTTP adapter health)
  3) Updates last_health_at; marks failed when unhealthy
  4) Optional auto-repair for serverless (TBE_HOST_AUTO_REPAIR=1) with cooldown

Strong path: real probes, not theatre. No vendor names in user alerts.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("tbe.hosting.health_monitor")

_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def interval_sec() -> float:
    try:
        return max(10.0, float((os.environ.get("TBE_HOST_HEALTH_INTERVAL") or "30").strip()))
    except Exception:
        return 30.0


def auto_repair_enabled() -> bool:
    return (os.environ.get("TBE_HOST_AUTO_REPAIR") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def repair_cooldown_sec() -> float:
    try:
        return max(60.0, float((os.environ.get("TBE_HOST_REPAIR_COOLDOWN") or "300").strip()))
    except Exception:
        return 300.0


def _serverless_http_probe(inst) -> tuple[bool, str]:
    """GET public URL / webhook path — same adapter contract as phase-3 verify."""
    base = str(getattr(inst, "public_base_url", "") or "").rstrip("/")
    diag = dict(getattr(inst, "last_diagnosis", None) or {})
    path = str(diag.get("webhook_path") or "/api")
    if not path.startswith("/"):
        path = "/" + path
    if not base.startswith("https://"):
        # fallback: webhook_public_url may be full hook URL
        hook = str(getattr(inst, "webhook_public_url", "") or diag.get("webhook_url") or "")
        if hook.startswith("https://"):
            base = hook
            path = ""
        else:
            return False, "no_public_url"
    try:
        from lumen.hosting.serverless_verify import health_check_deployment, normalize_public_url

        if path:
            result = health_check_deployment(
                normalize_public_url(base),
                webhook_path=path,
                retries=2,
                delay_sec=0.5,
                timeout=10.0,
            )
        else:
            result = health_check_deployment(
                normalize_public_url(base),
                webhook_path="/api",
                retries=2,
                delay_sec=0.5,
                timeout=10.0,
            )
        if result.get("ok"):
            return True, "http_ok"
        return False, str(result.get("error") or result.get("status") or "http_unhealthy")
    except Exception as exc:
        return False, f"probe_{type(exc).__name__}"


def check_instance(inst, *, get_backend_status: Callable | None = None) -> tuple[bool, str]:
    """Return (healthy, reason)."""
    dep = (getattr(inst, "deployment_id", None) or "").strip()
    backend = (getattr(inst, "sandbox_backend", None) or "").strip().lower()

    if backend in {"lumen_serverless", "serverless", "vercel"}:
        return _serverless_http_probe(inst)

    if not dep:
        return False, "no_deployment_id"
    try:
        if get_backend_status is not None:
            return get_backend_status(inst)
        from lumen.engine.services.sandbox_runtime.firecracker_backend import (
            FirecrackerSandboxBackend,
        )

        b = FirecrackerSandboxBackend()
        if not hasattr(b, "status"):
            return True, "backend_no_status_method"
        handle = b.status(dep)
        st = (getattr(handle, "status", None) or "").lower()
        if st in {"running", "starting"}:
            return True, st
        return False, st or "unknown"
    except Exception as exc:
        return False, f"{type(exc).__name__}:{exc}"[:200]


def _try_auto_repair(hosting_service, inst) -> bool:
    """One repair attempt for serverless when enabled; respects cooldown."""
    if not auto_repair_enabled():
        return False
    backend = str(getattr(inst, "sandbox_backend", "") or "").lower()
    if backend not in {"lumen_serverless", "serverless", "vercel"}:
        return False
    diag = dict(getattr(inst, "last_diagnosis", None) or {})
    last = float(diag.get("last_auto_repair_at") or 0)
    if last and (time.time() - last) < repair_cooldown_sec():
        return False
    path = str(getattr(inst, "project_path", "") or "")
    if not path:
        return False
    token = ""
    try:
        from lumen.hosting.secrets_env import load_project_secrets
        sealed = load_project_secrets(path)
        token = (sealed.get("BOT_TOKEN") or sealed.get("TELEGRAM_BOT_TOKEN") or "").strip()
    except Exception:
        token = ""
    if not token or ":" not in token:
        diag["auto_repair_skipped"] = "no_sealed_token"
        inst.last_diagnosis = diag
        return False
    try:
        from lumen.hosting.serverless_repair import repair_serverless_project
        from lumen.hosting.agent_host_pipeline import attach_serverless_instance

        rep = repair_serverless_project(
            path,
            bot_token=token,
            user_id=int(getattr(inst, "user_id", 0) or 0),
            service_name=f"lumen-u{int(getattr(inst, 'user_id', 0) or 0)}-heal",
        )
        diag["last_auto_repair_at"] = time.time()
        if not rep.ok:
            diag["auto_repair_ok"] = False
            diag["auto_repair_error"] = (rep.message or "")[:200]
            inst.last_diagnosis = diag
            return False
        meta = dict(rep.meta or {})
        meta["from_repair"] = True
        meta["auto_repair"] = True
        attach_serverless_instance(
            hosting_service,
            user_id=int(getattr(inst, "user_id", 0) or 0),
            project_path=path,
            bot_token=token,
            tenant_id=str(getattr(inst, "tenant_id", "") or ""),
            deployment_id=rep.deployment_id,
            public_url=rep.url,
            webhook_url=str(meta.get("webhook_url") or getattr(inst, "webhook_public_url", "") or ""),
            meta=meta,
            instance_id=str(getattr(inst, "instance_id", "") or ""),
        )
        diag["auto_repair_ok"] = True
        diag["lifecycle_state"] = str(meta.get("lifecycle_state") or "RUNNING")
        diag["verify_ok"] = bool(meta.get("verify_ok", True))
        # attach may replace inst in map — mark success on returned path
        inst.status = "running"
        inst.last_error = ""
        inst.last_diagnosis = {**dict(getattr(inst, "last_diagnosis", None) or {}), **diag}
        return True
    except Exception as exc:
        logger.warning("auto_repair failed: %s", type(exc).__name__)
        diag["auto_repair_ok"] = False
        diag["auto_repair_error"] = type(exc).__name__
        inst.last_diagnosis = diag
        return False


def run_once(hosting_service) -> dict:
    """Probe all running instances."""
    stats: dict[str, Any] = {"checked": 0, "healthy": 0, "failed": 0, "repaired": 0}
    try:
        instances = list((getattr(hosting_service, "_instances", None) or {}).values())
    except Exception:
        instances = []
    now = time.time()
    for inst in instances:
        if (getattr(inst, "status", "") or "") != "running":
            continue
        stats["checked"] += 1
        ok, reason = check_instance(inst)
        if ok:
            stats["healthy"] += 1
            try:
                inst.last_health_at = now
                inst.last_error = ""
                diag = dict(getattr(inst, "last_diagnosis", None) or {})
                diag["last_health_reason"] = reason
                diag["last_health_ok"] = True
                inst.last_diagnosis = diag
            except Exception:
                pass
            continue

        # Unhealthy
        repaired = _try_auto_repair(hosting_service, inst)
        if repaired:
            stats["repaired"] += 1
            stats["healthy"] += 1
            try:
                inst.last_health_at = now
                inst.status = "running"
                inst.last_error = ""
            except Exception:
                pass
            logger.info(
                "host auto-repaired instance=%s",
                getattr(inst, "instance_id", ""),
            )
            continue

        stats["failed"] += 1
        try:
            inst.status = "failed"
            inst.last_error = f"health_failed:{reason}"[:400]
            inst.last_health_at = now
            diag = dict(getattr(inst, "last_diagnosis", None) or {})
            diag["last_health_ok"] = False
            diag["last_health_reason"] = reason
            diag["lifecycle_state"] = "FAILED"
            inst.last_diagnosis = diag
        except Exception:
            pass
        logger.warning(
            "host health failed instance=%s reason=%s",
            getattr(inst, "instance_id", ""),
            reason,
        )
        try:
            from lumen.hosting.alerter import alert_instance_failed
            alert_instance_failed(
                instance_id=str(getattr(inst, "instance_id", "")),
                user_id=int(getattr(inst, "user_id", 0) or 0),
                reason=str(reason),
                deployment_id=str(getattr(inst, "deployment_id", "") or ""),
            )
        except Exception:
            pass
        try:
            from lumen.hosting.log_aggregator import aggregate_and_ship
            aggregate_and_ship(
                str(getattr(inst, "instance_id", "")),
                str(getattr(inst, "deployment_id", "") or ""),
            )
        except Exception:
            pass
        # Stop dead FC deployment only
        try:
            backend = str(getattr(inst, "sandbox_backend", "") or "").lower()
            dep = (getattr(inst, "deployment_id", None) or "").strip()
            if dep and backend not in {"lumen_serverless", "serverless", "vercel"}:
                from lumen.engine.services.sandbox_runtime.firecracker_backend import (
                    FirecrackerSandboxBackend,
                )
                FirecrackerSandboxBackend().stop(dep)
        except Exception:
            pass
    try:
        if hasattr(hosting_service, "_save"):
            hosting_service._save()
    except Exception:
        logger.exception("health_monitor save failed")
    return stats


def _loop(get_service: Callable) -> None:
    while not _stop.is_set():
        try:
            svc = get_service()
            if svc is not None:
                run_once(svc)
        except Exception:
            logger.exception("health_monitor loop error")
        _stop.wait(interval_sec())


def start_background(get_service: Callable) -> None:
    """Start daemon thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    if (os.environ.get("TBE_HOST_HEALTH_MONITOR") or "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        logger.info("host health monitor disabled")
        return
    _stop.clear()
    _thread = threading.Thread(
        target=_loop, args=(get_service,), name="lumen-host-health", daemon=True
    )
    _thread.start()
    logger.info("host health monitor started interval=%ss", interval_sec())


def stop_background() -> None:
    _stop.set()


__all__ = [
    "check_instance",
    "run_once",
    "start_background",
    "stop_background",
    "interval_sec",
    "auto_repair_enabled",
]
