#!/usr/bin/env python3
"""Credits health monitor — promo expiry enforcement + ledger drift detection.

Designed for cron / GitHub Actions schedule.

Checks:
  1. Wallets with promotional_balance > 0 and promo_expires_at in the past
     → force expire_promotional (burn leftover trial credits)
  2. Optional reconcile per tenant (when store supports listing)
  3. Exit non-zero if drift remains after expire (CREDITS_MONITOR_FAIL_ON_DRIFT=1)

Env:
  DATABASE_URL / POSTGRES_URL  — use Postgres store; else memory smoke only
  CREDITS_MONITOR_FAIL_ON_DRIFT — default 1
  CREDITS_MONITOR_TENANT_IDS   — comma list to scan (required for targeted reconcile
                                 when store cannot list all wallets)
  CREDITS_MONITOR_MAX_TENANTS  — cap (default 500)
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any


def _env_bool(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "off", "no"}


def _get_service():
    from b2b_platform.credits import get_credit_service, reset_credit_service_for_tests

    reset_credit_service_for_tests()
    return get_credit_service()


def _list_candidate_tenants(svc: Any) -> list[str]:
    explicit = (os.getenv("CREDITS_MONITOR_TENANT_IDS") or "").strip()
    if explicit:
        return [t.strip() for t in explicit.split(",") if t.strip()]

    store = getattr(svc, "_store", None)
    # Memory store: internal dict
    wallets = getattr(store, "_wallets", None)
    if isinstance(wallets, dict):
        return list(wallets.keys())

    # Postgres: best-effort query
    dsn = (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRESQL_URL")
        or ""
    ).strip()
    if dsn and store is not None and hasattr(store, "_conn"):
        try:
            max_n = int(os.getenv("CREDITS_MONITOR_MAX_TENANTS") or "500")
            with store._conn() as conn:  # noqa: SLF001 — monitor privilege
                rows = conn.execute(
                    """
                    SELECT tenant_id FROM credit_wallets
                    WHERE promotional_balance > 0
                       OR current_balance <> 0
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (max_n,),
                ).fetchall()
            return [str(r["tenant_id"] if isinstance(r, dict) else r[0]) for r in rows]
        except Exception as exc:
            print(json.dumps({"warn": "pg_list_failed", "error": str(exc)[:200]}))
    return []


def _smoke_memory_paths(svc: Any) -> dict[str, Any]:
    """Self-test: grant expired promo → monitor must burn it."""
    from b2b_platform.credits.service import CreditService
    from b2b_platform.credits.memory_store import MemoryCreditsStore

    local = CreditService(MemoryCreditsStore())
    tid = f"monitor-smoke-{int(time.time())}"
    r = local.credit_credits(
        tid,
        50,
        reason="welcome_grant",
        idempotency_key=f"welcome-grant-{tid}",
        promotional=True,
        promo_expires_at=time.time() - 60,
        metadata={"is_promotional": True, "source": "monitor_smoke"},
    )
    if not r.ok:
        return {"ok": False, "phase": "grant", "reason": r.reason}
    # Read store directly (service.get_wallet would auto-expire)
    raw_before = local._store.get_wallet(tid)  # noqa: SLF001
    before_bal = int(raw_before.current_balance)
    before_promo = int(raw_before.promotional_balance)
    if before_bal < 50 or before_promo < 50:
        return {
            "ok": False,
            "phase": "grant_persist",
            "before_balance": before_bal,
            "before_promo": before_promo,
            "reason": "expected_50_promo_after_grant",
        }
    expired = local.expire_promotional(tid)
    after = local.get_wallet(tid)
    recon = local.reconcile(tid)
    ok = (
        after.current_balance == 0
        and after.promotional_balance == 0
        and recon.ok
        and expired.reason == "promo_expired"
    )
    return {
        "ok": ok,
        "phase": "smoke",
        "before_balance": before_bal,
        "before_promo": before_promo,
        "expire_reason": expired.reason,
        "after_balance": after.current_balance,
        "reconcile_ok": recon.ok,
    }


def run() -> int:
    fail_on_drift = _env_bool("CREDITS_MONITOR_FAIL_ON_DRIFT", True)
    report: dict[str, Any] = {
        "ts": time.time(),
        "smoke": None,
        "scanned": 0,
        "expired": 0,
        "drift": [],
        "errors": [],
    }

    # Always run in-process smoke (works without DATABASE_URL)
    try:
        report["smoke"] = _smoke_memory_paths(_get_service())
    except Exception as exc:
        report["smoke"] = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
        report["errors"].append("smoke_failed")

    svc = _get_service()
    tenants = _list_candidate_tenants(svc)
    report["tenant_count_listed"] = len(tenants)

    for tid in tenants:
        report["scanned"] += 1
        try:
            # Force expiry path
            exp = svc.expire_promotional(tid)
            if exp.reason == "promo_expired":
                report["expired"] += 1
            w = svc.get_wallet(tid)
            recon = svc.reconcile(tid)
            if not recon.ok or int(getattr(recon, "drift_balance", 0) or 0) != 0:
                report["drift"].append(
                    {
                        "tenant_id": tid,
                        "wallet_balance": int(w.current_balance),
                        "promo": int(w.promotional_balance),
                        "reconcile_ok": bool(recon.ok),
                        "drift_balance": int(getattr(recon, "drift_balance", 0) or 0),
                        "notes": getattr(recon, "notes", "") or "",
                    }
                )
            # Stale promo still present after expire = bug
            if int(w.promotional_balance) > 0 and float(w.promo_expires_at or 0) > 0:
                if time.time() >= float(w.promo_expires_at):
                    report["drift"].append(
                        {
                            "tenant_id": tid,
                            "issue": "stale_promotional_after_expire",
                            "promo": int(w.promotional_balance),
                            "promo_expires_at": float(w.promo_expires_at),
                        }
                    )
        except Exception as exc:
            report["errors"].append({"tenant_id": tid, "error": f"{type(exc).__name__}:{exc}"})

    smoke_ok = bool((report.get("smoke") or {}).get("ok"))
    has_drift = bool(report["drift"])
    has_errors = bool(report["errors"])

    report["ok"] = smoke_ok and not (fail_on_drift and has_drift) and not has_errors
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not smoke_ok:
        return 2
    if fail_on_drift and has_drift:
        return 3
    if has_errors:
        return 4
    return 0


if __name__ == "__main__":
    # Ensure repo root on path
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    raise SystemExit(run())
