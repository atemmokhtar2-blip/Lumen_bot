"""Phase 4 — zero-balance graceful degradation.

Threshold alerts (80/90/95), limited grace/overdraft window, then safe suspend.
Does not invent charge logic — observes CreditService wallet + rating failures.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

THRESHOLDS = (80, 90, 95)
GRACE_SEC = int(os.getenv("TBE_BALANCE_GRACE_SEC") or "1800")  # 30 min default
ALERT_COOLDOWN_SEC = int(os.getenv("TBE_BALANCE_ALERT_COOLDOWN_SEC") or "600")


@dataclass
class TenantBalanceState:
    tenant_id: str
    last_alert_pct: int = 0
    last_alert_at: float = 0.0
    grace_started_at: float = 0.0
    grace_until: float = 0.0
    suspended: bool = False
    suspended_at: float = 0.0
    suspend_reason: str = ""
    alerts_sent: list[str] = field(default_factory=list)


@dataclass
class LifecycleAction:
    ok: bool
    action: str  # none | alert | enter_grace | suspend | already_suspended
    detail: str = ""
    state: Optional[TenantBalanceState] = None


class MemoryLifecycleStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, TenantBalanceState] = {}

    def get(self, tenant_id: str) -> TenantBalanceState:
        with self._lock:
            tid = str(tenant_id)
            if tid not in self._states:
                self._states[tid] = TenantBalanceState(tenant_id=tid)
            return self._states[tid]

    def save(self, state: TenantBalanceState) -> None:
        with self._lock:
            self._states[str(state.tenant_id)] = state


_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS balance_lifecycle (
    tenant_id TEXT PRIMARY KEY,
    last_alert_pct INTEGER NOT NULL DEFAULT 0,
    last_alert_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    grace_started_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    grace_until DOUBLE PRECISION NOT NULL DEFAULT 0,
    suspended BOOLEAN NOT NULL DEFAULT FALSE,
    suspended_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    suspend_reason TEXT NOT NULL DEFAULT '',
    alerts_sent JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
);
"""


class PostgresLifecycleStore:
    def __init__(self, dsn: str) -> None:
        import psycopg
        from psycopg.rows import dict_row
        self.dsn = dsn
        self._psycopg = psycopg
        self._dict_row = dict_row
        with self._conn() as conn:
            conn.execute(_PG_SCHEMA)
            conn.commit()

    def _conn(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def get(self, tenant_id: str) -> TenantBalanceState:
        import json
        tid = str(tenant_id)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM balance_lifecycle WHERE tenant_id=%s", (tid,)
            ).fetchone()
            if not row:
                return TenantBalanceState(tenant_id=tid)
            alerts = row.get("alerts_sent") or []
            if isinstance(alerts, str):
                try:
                    alerts = json.loads(alerts)
                except Exception:
                    alerts = []
            return TenantBalanceState(
                tenant_id=tid,
                last_alert_pct=int(row.get("last_alert_pct") or 0),
                last_alert_at=float(row.get("last_alert_at") or 0),
                grace_started_at=float(row.get("grace_started_at") or 0),
                grace_until=float(row.get("grace_until") or 0),
                suspended=bool(row.get("suspended")),
                suspended_at=float(row.get("suspended_at") or 0),
                suspend_reason=str(row.get("suspend_reason") or ""),
                alerts_sent=list(alerts) if isinstance(alerts, list) else [],
            )

    def save(self, state: TenantBalanceState) -> None:
        import json
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO balance_lifecycle (
                    tenant_id, last_alert_pct, last_alert_at, grace_started_at, grace_until,
                    suspended, suspended_at, suspend_reason, alerts_sent, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    last_alert_pct=EXCLUDED.last_alert_pct,
                    last_alert_at=EXCLUDED.last_alert_at,
                    grace_started_at=EXCLUDED.grace_started_at,
                    grace_until=EXCLUDED.grace_until,
                    suspended=EXCLUDED.suspended,
                    suspended_at=EXCLUDED.suspended_at,
                    suspend_reason=EXCLUDED.suspend_reason,
                    alerts_sent=EXCLUDED.alerts_sent,
                    updated_at=EXCLUDED.updated_at
                """,
                (
                    state.tenant_id, state.last_alert_pct, state.last_alert_at,
                    state.grace_started_at, state.grace_until, state.suspended,
                    state.suspended_at, state.suspend_reason,
                    json.dumps(state.alerts_sent), time.time(),
                ),
            )
            conn.commit()


def _notify(tenant_id: str, level: str, message: str) -> None:
    """Best-effort notify — log + optional webhook."""
    logger.warning("balance_alert tenant=%s level=%s msg=%s", tenant_id, level, message)
    url = (os.getenv("TBE_BALANCE_ALERT_WEBHOOK") or "").strip()
    if not url:
        return
    try:
        import json
        import urllib.request
        data = json.dumps({"tenant_id": tenant_id, "level": level, "message": message}).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        logger.debug("alert webhook failed: %s", type(exc).__name__)


def _suspend_tenant_bots(tenant_id: str) -> dict[str, Any]:
    """Graceful stop of managed containers labeled with tenant."""
    stopped = 0
    try:
        from telegram_bot_engine.services.sandbox_runtime.supervisor import (
            list_managed_containers,
            _docker,
        )
        for c in list_managed_containers():
            labels = c.get("labels") if isinstance(c.get("labels"), dict) else {}
            tid = str(labels.get("tbe.tenant_id") or c.get("tenant_id") or "")
            if tid != str(tenant_id):
                continue
            cid = str(c.get("id") or "")
            if not cid:
                continue
            # graceful stop then force
            _docker(["stop", "-t", "15", cid], timeout=30)
            _docker(["rm", "-f", cid], timeout=20)
            stopped += 1
            logger.warning("suspended bot container %s tenant=%s", cid[:12], tenant_id)
    except Exception as exc:
        logger.warning("suspend bots failed: %s", type(exc).__name__)
        return {"ok": False, "stopped": stopped, "error": type(exc).__name__}
    return {"ok": True, "stopped": stopped}


class BalanceLifecycle:
    def __init__(self, store: Any, credit_service: Any, *, baseline_balance: Optional[dict[str, int]] = None) -> None:
        self._store = store
        self._credits = credit_service
        # optional funded baseline for % calculation (else use current+spent heuristic)
        self._baseline = baseline_balance or {}

    def _pct_used(self, tenant_id: str) -> tuple[int, int, int]:
        """Return (pct_used 0-100, available, current)."""
        w = self._credits.get_wallet(str(tenant_id))
        available = int(w.available)
        current = int(w.current_balance)
        baseline = int(self._baseline.get(str(tenant_id)) or 0)
        if baseline <= 0:
            # use current as remaining of unknown total → pct only when low absolute
            if available <= 0:
                return 100, available, current
            return 0, available, current
        used = max(0, baseline - available)
        pct = int(min(100, (used * 100) // baseline)) if baseline else 0
        return pct, available, current

    def set_baseline(self, tenant_id: str, amount: int) -> None:
        self._baseline[str(tenant_id)] = max(0, int(amount))

    def on_balance_changed(self, tenant_id: str) -> LifecycleAction:
        tid = str(tenant_id)
        state = self._store.get(tid)
        if state.suspended:
            return LifecycleAction(True, "already_suspended", state=state)

        pct, available, current = self._pct_used(tid)
        now = time.time()

        # Zero / insufficient takes priority over % alerts
        if available <= 0:
            return self._enter_or_progress_grace(tid, state, reason="available_zero")

        # Threshold alerts
        for th in THRESHOLDS:
            if pct >= th and state.last_alert_pct < th:
                if now - state.last_alert_at >= ALERT_COOLDOWN_SEC or state.last_alert_pct < th:
                    msg = f"Credits usage reached {th}% (available={available})"
                    _notify(tid, f"threshold_{th}", msg)
                    state.last_alert_pct = th
                    state.last_alert_at = now
                    state.alerts_sent.append(f"{th}@{int(now)}")
                    self._store.save(state)
                    return LifecycleAction(True, "alert", detail=msg, state=state)

        # Recovered balance clears grace if not suspended
        if state.grace_until > 0 and available > 0:
            state.grace_until = 0
            state.grace_started_at = 0
            self._store.save(state)
            return LifecycleAction(True, "grace_cleared", state=state)

        return LifecycleAction(True, "none", state=state)

    def on_rating_failure(self, tenant_id: str, reason: str) -> LifecycleAction:
        if "insufficient" not in (reason or ""):
            return LifecycleAction(True, "none", detail=reason)
        state = self._store.get(str(tenant_id))
        if state.suspended:
            return LifecycleAction(True, "already_suspended", state=state)
        return self._enter_or_progress_grace(str(tenant_id), state, reason=reason)

    def _enter_or_progress_grace(self, tid: str, state: TenantBalanceState, reason: str) -> LifecycleAction:
        now = time.time()
        if state.grace_until <= 0:
            state.grace_started_at = now
            state.grace_until = now + GRACE_SEC
            self._store.save(state)
            _notify(tid, "grace_started", f"Grace period {GRACE_SEC}s due to {reason}")
            return LifecycleAction(True, "enter_grace", detail=reason, state=state)

        if now < state.grace_until:
            # periodic warning every cooldown
            if now - state.last_alert_at >= ALERT_COOLDOWN_SEC:
                left = int(state.grace_until - now)
                _notify(tid, "grace_warning", f"Grace remaining ~{left}s ({reason})")
                state.last_alert_at = now
                self._store.save(state)
            return LifecycleAction(True, "in_grace", detail=reason, state=state)

        return self.suspend(tid, reason=f"grace_expired:{reason}")

    def suspend(self, tenant_id: str, *, reason: str = "balance") -> LifecycleAction:
        tid = str(tenant_id)
        state = self._store.get(tid)
        if state.suspended:
            return LifecycleAction(True, "already_suspended", state=state)
        result = _suspend_tenant_bots(tid)
        state.suspended = True
        state.suspended_at = time.time()
        state.suspend_reason = reason[:200]
        self._store.save(state)
        _notify(tid, "suspended", f"Bots suspended: {reason}; stopped={result.get('stopped')}")
        return LifecycleAction(True, "suspend", detail=str(result), state=state)

    def clear_suspension_on_credit(self, tenant_id: str) -> LifecycleAction:
        """Call after successful top-up — unsuspend flag only (bots restart via host API)."""
        state = self._store.get(str(tenant_id))
        state.suspended = False
        state.suspended_at = 0
        state.suspend_reason = ""
        state.grace_until = 0
        state.grace_started_at = 0
        state.last_alert_pct = 0
        self._store.save(state)
        _notify(str(tenant_id), "unsuspended", "Balance restored — suspension cleared")
        return LifecycleAction(True, "unsuspended", state=state)

    def is_hosting_allowed(self, tenant_id: str) -> tuple[bool, str]:
        state = self._store.get(str(tenant_id))
        if state.suspended:
            return False, "suspended_due_to_balance"
        w = self._credits.get_wallet(str(tenant_id))
        if w.available <= 0 and state.grace_until <= time.time():
            # no active grace
            if state.grace_until == 0:
                return False, "insufficient_balance"
        return True, "ok"

    def tick(self, tenant_ids: list[str] | None = None) -> dict[str, Any]:
        """Periodic: progress grace → suspend for known tenants with zero balance."""
        actions = []
        ids = tenant_ids or []
        if not ids and hasattr(self._store, "_states"):
            ids = list(self._store._states.keys())
        for tid in ids:
            act = self.on_balance_changed(tid)
            if act.action not in {"none", "already_suspended"}:
                actions.append({"tenant_id": tid, "action": act.action, "detail": act.detail})
        return {"actions": actions}


_LC: BalanceLifecycle | None = None


def get_balance_lifecycle() -> BalanceLifecycle:
    global _LC
    if _LC is not None:
        return _LC
    from b2b_platform.credits import get_credit_service
    dsn = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    store: Any = PostgresLifecycleStore(dsn) if dsn else MemoryLifecycleStore()
    _LC = BalanceLifecycle(store, get_credit_service())
    return _LC


def reset_balance_lifecycle_for_tests() -> None:
    global _LC
    _LC = None
