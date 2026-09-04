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

import math

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
        "requests": request_count(getattr(inst, "instance_id", "") or ""),
    }


def compute_credits(usage: dict[str, Any]) -> float:
    credits = 0.0
    credits += _fenv("TBE_HOST_CREDIT_PER_MINUTE", 0.01) * float(usage.get("host_minutes") or 0)
    credits += _fenv("TBE_HOST_CREDIT_PER_RAM_MB_HOUR", 0.0001) * float(usage.get("ram_mb_hours") or 0)
    credits += _fenv("TBE_HOST_CREDIT_PER_CPU_HOUR", 0.05) * float(usage.get("cpu_core_hours") or 0)
    credits += _fenv("TBE_HOST_CREDIT_PER_STORAGE_GB_HOUR", 0.002) * float(
        usage.get("storage_gb_hours") or 0
    )
    credits += _fenv("TBE_HOST_CREDIT_PER_REQUEST", 0.0001) * float(usage.get("requests") or 0)
    return round(max(0.0, credits), 6)


def settle_instance(inst: Any, *, tenant_id: str | None = None) -> dict[str, Any]:
    """Record metering + credit debit when instance stops.

    ROOT FIX: always resolve tenant (tg:{user_id}), convert fractional host
    credits to integer credits, deduct via CreditService.deduct_credits with
    idempotency on instance_id (never call non-existent debit/consume).
    """
    usage = compute_session_usage(inst)
    credits_f = float(compute_credits(usage) or 0.0)
    amount = int(math.ceil(credits_f)) if credits_f > 0 else 0
    usage["credits"] = credits_f
    usage["credits_charged"] = amount

    uid = int(getattr(inst, "user_id", 0) or 0)
    tid = str(tenant_id or "").strip()
    if not tid and uid:
        tid = f"tg:{uid}"
    usage["tenant_id"] = tid

    try:
        from lumen.platform.metering import get_metering

        get_metering().record(
            str(tid or uid or "unknown"),
            host_minutes=float(usage["host_minutes"]),
            event="host_session_settle",
        )
    except Exception as exc:
        logger.warning("metering record failed: %s", type(exc).__name__)

    if amount > 0 and tid:
        try:
            from lumen.platform.credits import get_credit_service

            svc = get_credit_service()
            iid = str(usage.get("instance_id") or "host")
            result = svc.deduct_credits(
                tid,
                amount,
                reason="host_usage",
                reference_id=iid,
                idempotency_key=f"host_settle:{tid}:{iid}",
                metadata={
                    "host_minutes": usage.get("host_minutes"),
                    "cpu_core_hours": usage.get("cpu_core_hours"),
                    "ram_mb_hours": usage.get("ram_mb_hours"),
                    "credits_float": credits_f,
                },
            )
            usage["credit_result"] = {
                "ok": bool(getattr(result, "ok", False)),
                "reason": str(getattr(result, "reason", "") or ""),
                "balance": int(getattr(getattr(result, "wallet", None), "current_balance", 0) or 0),
            }
            # Stop future hosting if balance exhausted
            if not getattr(result, "ok", False):
                try:
                    from lumen.platform.balance_lifecycle import get_balance_lifecycle
                    get_balance_lifecycle().on_balance_changed(tid)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("credit deduct host_usage failed: %s", type(exc).__name__)
            usage["credit_result"] = {"ok": False, "reason": type(exc).__name__}
    return usage


__all__ = [
    "compute_session_usage",
    "compute_credits",
    "settle_instance",
    "project_storage_bytes",
]


def record_request(instance_id: str, n: int = 1) -> None:
    """Increment request counter for an instance (Redis)."""
    try:
        from lumen.engine.services.hosting.redis_state import _client
        r = _client()
        if r is None:
            return
        key = f"lumen:host:req:{instance_id}"
        r.incrby(key, int(n))
        r.expire(key, 86400 * 7)
    except Exception:
        pass


def request_count(instance_id: str) -> int:
    try:
        from lumen.engine.services.hosting.redis_state import _client
        r = _client()
        if r is None:
            return 0
        return int(r.get(f"lumen:host:req:{instance_id}") or 0)
    except Exception:
        return 0
