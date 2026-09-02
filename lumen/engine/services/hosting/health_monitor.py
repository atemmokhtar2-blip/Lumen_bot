"""Periodic health checks for PERMANENT_HOST instances (orchestrator-side).

Every ~30s (configurable) the monitor:
  1) Lists running HostInstance records
  2) Asks the sandbox backend for status
  3) Updates last_health_at / marks failed when the VM is gone

This is the strong alternative to Dockerfile HEALTHCHECK alone: checks run
against the real Firecracker/process plane, not only container metadata.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("tbe.hosting.health_monitor")

_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def interval_sec() -> float:
    try:
        return max(10.0, float((os.environ.get("TBE_HOST_HEALTH_INTERVAL") or "30").strip()))
    except Exception:
        return 30.0


def check_instance(inst, *, get_backend_status: Callable | None = None) -> tuple[bool, str]:
    """Return (healthy, reason)."""
    dep = (getattr(inst, "deployment_id", None) or "").strip()
    backend = (getattr(inst, "sandbox_backend", None) or "").strip()
    if not dep:
        return False, "no_deployment_id"
    try:
        if get_backend_status is not None:
            return get_backend_status(inst)
        # Permanent host health is Firecracker-plane only (no docker status confusion)
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


def run_once(hosting_service) -> dict:
    """Probe all running instances owned by this node/process registry."""
    stats = {"checked": 0, "healthy": 0, "failed": 0}
    try:
        instances = list(getattr(hosting_service, "_instances", {}) or {}).values()
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
            except Exception:
                pass
        else:
            stats["failed"] += 1
            try:
                inst.status = "failed"
                inst.last_error = f"health_failed:{reason}"[:400]
                inst.last_health_at = now
            except Exception:
                pass
            logger.warning(
                "host health failed instance=%s reason=%s",
                getattr(inst, "instance_id", ""),
                reason,
            )
    try:
        if hasattr(hosting_service, "_save"):
            hosting_service._save()
    except Exception:
        logger.exception("health monitor save failed")
    return stats


def _loop(get_service: Callable) -> None:
    while not _stop.is_set():
        try:
            svc = get_service()
            if svc is not None:
                run_once(svc)
        except Exception:
            logger.exception("health monitor iteration failed")
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
]
