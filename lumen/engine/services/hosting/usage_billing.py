"""Detailed host usage → credits/metering.

Cost model (per instance session):
  host_minutes = (now - started_at) / 60
  ram_mb_hours = (policy max_memory MB) * (host_minutes / 60)
  cpu_core_hours = (policy max_cpus) * (host_minutes / 60)
  storage_gb = project tree size / 1GiB (sampled)

Config pricing (credits):
  TBE_HOST_CREDIT_PER_MINUTE=0.01
  TBE_HOST_CREDIT_PER_RAM_MB_HOUR=0.0001
  TBE_HOST_CREDIT_PER_CPU_HOUR=0.05
  TBE_HOST_CREDIT_PER_STORAGE_GB_HOUR=0.002
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("tbe.hosting.usage_billing")


def _fenv(name: str, default: float) -> float:
    try:
        return float((os.environ.get(name) or str(default)).strip())
    except Exception:
        return default


def project_storage_bytes(project_path: str | Path) -> int:
    root = Path(project_path)
    total = 0
    if not root.is_dir():
        return 0
    try:
        for p in root.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except Exception:
                pass
    except Exception:
        return total
    return total


def policy_resources() -> tuple[float, float]:
    """Return (cpu_cores, ram_mb) from sandbox policy defaults."""
    try:
        from lumen.engine.services.sandbox_runtime.policy import load_policy

        pol = load_policy()
        # max_cpus may be string "0.5"
        cpu = float(getattr(pol, "max_cpus", 0.5) or 0.5)
        mem_s = str(getattr(pol, "max_memory", "256m") or "256m").lower()
        ram = 256.0
        if mem_s.endswith("g"):
            ram = float(mem_s[:-1]) * 1024
        elif mem_s.endswith("m"):
            ram = float(mem_s[:-1])
        return max(0.1, cpu), max(64.0, ram)
    except Exception:
        return 0.5, 256.0


def compute_session_usage(inst: Any, *, ended_at: float | None = None) -> dict[str, Any]:
    started = float(getattr(inst, "started_at", 0) or 0)
    end = float(ended_at if ended_at is not None else time.time())
    if started <= 0:
        minutes = 0.0
    else:
        minutes = max(0.0, (end - started) / 60.0)
    cpu, ram_mb = policy_resources()
    hours = minutes / 60.0
    storage_b = project_storage_bytes(getattr(inst, "project_path", "") or "")
    storage_gb = storage_b / (1024**3)
    return {
        "instance_id": getattr(inst, "instance_id", ""),
        "user_id": getattr(inst, "user_id", 0),
        "host_minutes": round(minutes, 4),
        "cpu_cores": cpu,
        "ram_mb": ram_mb,
        "cpu_core_hours": round(cpu * hours, 6),
        "ram_mb_hours": round(ram_mb * hours, 4),
        "storage_bytes": storage_b,
        "storage_gb_hours": round(storage_gb * hours, 6),
        "started_at": started,
        "ended_at": end,
    }


def compute_credits(usage: dict[str, Any]) -> float:
    credits = 0.0
    credits += _fenv("TBE_HOST_CREDIT_PER_MINUTE", 0.01) * float(usage.get("host_minutes") or 0)
    credits += _fenv("TBE_HOST_CREDIT_PER_RAM_MB_HOUR", 0.0001) * float(usage.get("ram_mb_hours") or 0)
    credits += _fenv("TBE_HOST_CREDIT_PER_CPU_HOUR", 0.05) * float(usage.get("cpu_core_hours") or 0)
    credits += _fenv("TBE_HOST_CREDIT_PER_STORAGE_GB_HOUR", 0.002) * float(
        usage.get("storage_gb_hours") or 0
    )
    return round(max(0.0, credits), 6)


def settle_instance(inst: Any, *, tenant_id: str | None = None) -> dict[str, Any]:
    """Record metering + optional credit debit when instance stops."""
    usage = compute_session_usage(inst)
    credits = compute_credits(usage)
    usage["credits"] = credits
    try:
        from lumen.platform.metering import get_metering

        get_metering().record(
            str(tenant_id or getattr(inst, "user_id", "") or "unknown"),
            host_minutes=float(usage["host_minutes"]),
            event="host_session_settle",
        )
    except Exception as exc:
        logger.warning("metering record failed: %s", type(exc).__name__)
    if credits > 0 and tenant_id:
        try:
            from lumen.platform.credits import get_credit_service

            # Best-effort debit; services differ by implementation
            svc = get_credit_service()
            if hasattr(svc, "debit"):
                svc.debit(tenant_id, credits, reason="host_usage", reference=usage["instance_id"])
            elif hasattr(svc, "consume"):
                svc.consume(tenant_id, credits, reason="host_usage")
        except Exception as exc:
            logger.warning("credit debit failed: %s", type(exc).__name__)
    return usage


__all__ = [
    "compute_session_usage",
    "compute_credits",
    "settle_instance",
    "project_storage_bytes",
]
