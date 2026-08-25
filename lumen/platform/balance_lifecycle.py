"""Phase 4 — world-class zero-balance lifecycle (state machine).

States: active → warning → grace → suspended → active

Baseline for % = max(explicit baseline, SUM of credit ledger legs on wallet that are inflows)
Grace is timed; suspend is idempotent; host_start is fail-closed when suspended.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

THRESHOLDS = (80, 90, 95)
GRACE_SEC = int(os.getenv("TBE_BALANCE_GRACE_SEC") or "1800")
ALERT_COOLDOWN_SEC = int(os.getenv("TBE_BALANCE_ALERT_COOLDOWN_SEC") or "600")
GRACE_WARN_EVERY_SEC = int(os.getenv("TBE_BALANCE_GRACE_WARN_SEC") or "600")  # every 10 min
FAIL_CLOSED_HOST = (os.getenv("TBE_BALANCE_FAIL_CLOSED") or "1").strip().lower() in {
    "1", "true", "yes", "on",
}


@dataclass
class TenantBalanceState:
    tenant_id: str
    phase: str = "active"  # active | warning | grace | suspended
    last_alert_pct: int = 0
    last_alert_at: float = 0.0
    grace_started_at: float = 0.0
    grace_until: float = 0.0
    last_grace_warn_at: float = 0.0
    suspended: bool = False
    suspended_at: float = 0.0
    suspend_reason: str = ""
    snapshot: dict[str, Any] = field(default_factory=dict)
    alerts_sent: list[str] = field(default_factory=list)
    baseline_credits: int = 0
    version: int = 0  # optimistic concurrency


@dataclass
class LifecycleAction:
    ok: bool
    action: str
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
            # return copy
            s = self._states[tid]
            return TenantBalanceState(**asdict(s))

    def save(self, state: TenantBalanceState) -> bool:
        """Optimistic save: version must match or be first write."""
        with self._lock:
            tid = str(state.tenant_id)
            cur = self._states.get(tid)
            if cur and cur.version != state.version:
                return False
            state.version = int(state.version) + 1
            self._states[tid] = TenantBalanceState(**asdict(state))
            return True

    def list_tenant_ids(self) -> list[str]:
        with self._lock:
            return list(self._states.keys())


_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS balance_lifecycle (
    tenant_id TEXT PRIMARY KEY,
    phase TEXT NOT NULL DEFAULT 'active',
    last_alert_pct INTEGER NOT NULL DEFAULT 0,
    last_alert_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    grace_started_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    grace_until DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_grace_warn_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    suspended BOOLEAN NOT NULL DEFAULT FALSE,
    suspended_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    suspend_reason TEXT NOT NULL DEFAULT '',
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    alerts_sent JSONB NOT NULL DEFAULT '[]'::jsonb,
    baseline_credits BIGINT NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 0,
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
        tid = str(tenant_id)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM balance_lifecycle WHERE tenant_id=%s", (tid,)
            ).fetchone()
        if not row:
            return TenantBalanceState(tenant_id=tid)
        snap = row.get("snapshot") or {}
        alerts = row.get("alerts_sent") or []
        if isinstance(snap, str):
            try:
                snap = json.loads(snap)
            except Exception:
                snap = {}
        if isinstance(alerts, str):
            try:
                alerts = json.loads(alerts)
            except Exception:
                alerts = []
        return TenantBalanceState(
            tenant_id=tid,
            phase=str(row.get("phase") or "active"),
            last_alert_pct=int(row.get("last_alert_pct") or 0),
            last_alert_at=float(row.get("last_alert_at") or 0),
            grace_started_at=float(row.get("grace_started_at") or 0),
            grace_until=float(row.get("grace_until") or 0),
            last_grace_warn_at=float(row.get("last_grace_warn_at") or 0),
            suspended=bool(row.get("suspended")),
            suspended_at=float(row.get("suspended_at") or 0),
            suspend_reason=str(row.get("suspend_reason") or ""),
            snapshot=dict(snap) if isinstance(snap, dict) else {},
            alerts_sent=list(alerts) if isinstance(alerts, list) else [],
            baseline_credits=int(row.get("baseline_credits") or 0),
            version=int(row.get("version") or 0),
        )

    def save(self, state: TenantBalanceState) -> bool:
        new_ver = int(state.version) + 1
        with self._conn() as conn:
            if state.version == 0:
                conn.execute(
                    """
                    INSERT INTO balance_lifecycle (
                        tenant_id, phase, last_alert_pct, last_alert_at, grace_started_at,
                        grace_until, last_grace_warn_at, suspended, suspended_at, suspend_reason,
                        snapshot, alerts_sent, baseline_credits, version, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                    ON CONFLICT (tenant_id) DO NOTHING
                    """,
                    (
                        state.tenant_id, state.phase, state.last_alert_pct, state.last_alert_at,
                        state.grace_started_at, state.grace_until, state.last_grace_warn_at,
                        state.suspended, state.suspended_at, state.suspend_reason,
                        json.dumps(state.snapshot), json.dumps(state.alerts_sent),
                        state.baseline_credits, new_ver, time.time(),
                    ),
                )
                # if conflict, try versioned update
            cur = conn.execute(
                """
                UPDATE balance_lifecycle SET
                    phase=%s, last_alert_pct=%s, last_alert_at=%s, grace_started_at=%s,
                    grace_until=%s, last_grace_warn_at=%s, suspended=%s, suspended_at=%s,
                    suspend_reason=%s, snapshot=%s::jsonb, alerts_sent=%s::jsonb,
                    baseline_credits=%s, version=%s, updated_at=%s
                WHERE tenant_id=%s AND version=%s
                """,
                (
                    state.phase, state.last_alert_pct, state.last_alert_at, state.grace_started_at,
                    state.grace_until, state.last_grace_warn_at, state.suspended, state.suspended_at,
                    state.suspend_reason, json.dumps(state.snapshot), json.dumps(state.alerts_sent),
                    state.baseline_credits, new_ver, time.time(),
                    state.tenant_id, int(state.version),
                ),
            )
            ok = cur.rowcount > 0
            if not ok and state.version == 0:
                # inserted fresh
                row = conn.execute(
                    "SELECT version FROM balance_lifecycle WHERE tenant_id=%s",
                    (state.tenant_id,),
                ).fetchone()
                ok = bool(row)
            conn.commit()
        if ok:
            state.version = new_ver
        return ok

    def list_tenant_ids(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT tenant_id FROM balance_lifecycle").fetchall()
        return [str(r["tenant_id"]) for r in rows]


def _notify(tenant_id: str, level: str, message: str, extra: Optional[dict] = None) -> None:
    payload = {
        "tenant_id": tenant_id,
        "level": level,
        "message": message,
        "ts": time.time(),
        **(extra or {}),
    }
    logger.warning("balance_alert %s", json.dumps(payload, ensure_ascii=False)[:500])
    url = (os.getenv("TBE_BALANCE_ALERT_WEBHOOK") or "").strip()
    if url:
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:
            logger.debug("webhook failed: %s", type(exc).__name__)
    # Optional Telegram to owner
    token = (os.getenv("TBE_PLATFORM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.getenv("TBE_BALANCE_ALERT_CHAT_ID") or "").strip()
    if token and chat:
        try:
            import urllib.parse
            import urllib.request
            text = f"[Lumen] {level}: {message} (tenant={tenant_id})"
            q = urllib.parse.urlencode({"chat_id": chat, "text": text[:3500]})
            urllib.request.urlopen(
                f"https://api.telegram.org/bot{token}/sendMessage?{q}", timeout=5
            )
        except Exception:
            pass


def _snapshot_and_stop(tenant_id: str) -> dict[str, Any]:
    """Capture running bot list then graceful stop."""
    stopped = 0
    bots: list[dict[str, str]] = []
    try:
        from lumen.engine.services.sandbox_runtime.supervisor import (
            list_managed_containers,
            _docker,
        )
        for c in list_managed_containers():
            labels = c.get("labels") if isinstance(c.get("labels"), dict) else {}
            tid = str(labels.get("tbe.tenant_id") or c.get("tenant_id") or "")
            if tid != str(tenant_id):
                continue
            cid = str(c.get("id") or "")
            bot_id = str(labels.get("tbe.bot_id") or c.get("bot_id") or c.get("name") or cid)[:120]
            bots.append({"container_id": cid[:64], "bot_id": bot_id, "status": str(c.get("status") or "")})
            if cid:
                code, _ = _docker(["stop", "-t", "20", cid], timeout=35)
                _docker(["rm", "-f", cid], timeout=20)
                if code == 0:
                    stopped += 1
                else:
                    # force path already rm -f
                    stopped += 1
    except Exception as exc:
        logger.warning("snapshot_stop failed: %s", type(exc).__name__)
        return {"ok": False, "stopped": stopped, "bots": bots, "error": type(exc).__name__}
    return {"ok": True, "stopped": stopped, "bots": bots}


def _funded_baseline(credit_service: Any, tenant_id: str, state_baseline: int) -> int:
    """Prefer max(state baseline, wallet current as floor, ledger purchases if available)."""
    try:
        w = credit_service.get_wallet(str(tenant_id))
        current = int(w.current_balance)
    except Exception:
        current = 0
    funded = max(int(state_baseline or 0), current)
    # Try sum of positive credit ops from list_ledger
    try:
        rows = credit_service.list_ledger(str(tenant_id), limit=500)
        inflow = 0
        for e in rows:
            amt = int(getattr(e, "amount", 0) or 0)
            if amt > 0:
                inflow += amt
            # double-entry: wallet credit legs
            for leg in getattr(e, "legs", []) or []:
                if getattr(leg, "side", "") == "credit" and str(getattr(leg, "account_id", "")).startswith("wallet:"):
                    inflow += int(getattr(leg, "amount", 0) or 0)
        if inflow > funded:
            funded = inflow
    except Exception:
        pass
    return max(funded, 0)


class BalanceLifecycle:
    def __init__(self, store: Any, credit_service: Any) -> None:
        self._store = store
        self._credits = credit_service

    def set_baseline(self, tenant_id: str, amount: int) -> None:
        state = self._store.get(str(tenant_id))
        state.baseline_credits = max(int(state.baseline_credits), int(amount))
        self._store.save(state)

    def status(self, tenant_id: str) -> dict[str, Any]:
        state = self._store.get(str(tenant_id))
        w = self._credits.get_wallet(str(tenant_id))
        baseline = _funded_baseline(self._credits, tenant_id, state.baseline_credits)
        available = int(w.available)
        pct = 0
        if baseline > 0:
            used = max(0, baseline - available)
            pct = int(min(100, (used * 100) // baseline))
        return {
            "tenant_id": str(tenant_id),
            "phase": state.phase,
            "suspended": state.suspended,
            "suspend_reason": state.suspend_reason,
            "grace_until": state.grace_until,
            "grace_remaining_sec": max(0, int(state.grace_until - time.time())) if state.grace_until else 0,
            "available": available,
            "current_balance": int(w.current_balance),
            "reserved_balance": int(w.reserved_balance),
            "baseline_credits": baseline,
            "pct_used": pct,
            "last_alert_pct": state.last_alert_pct,
            "snapshot": state.snapshot,
        }

    def on_balance_changed(self, tenant_id: str) -> LifecycleAction:
        tid = str(tenant_id)
        for _ in range(3):  # retry optimistic concurrency
            state = self._store.get(tid)
            if state.suspended or state.phase == "suspended":
                return LifecycleAction(True, "already_suspended", state=state)

            w = self._credits.get_wallet(tid)
            available = int(w.available)
            baseline = _funded_baseline(self._credits, tid, state.baseline_credits)
            if baseline > state.baseline_credits:
                state.baseline_credits = baseline
            pct = 0
            if baseline > 0:
                used = max(0, baseline - available)
                pct = int(min(100, (used * 100) // baseline))
            now = time.time()

            if available <= 0:
                act = self._grace_or_suspend(tid, state, reason="available_zero", now=now)
                if self._store.save(state) or act.action == "suspend":
                    return act
                continue

            # recovered
            if state.phase in {"grace", "warning"} and available > 0:
                state.phase = "active"
                state.grace_until = 0
                state.grace_started_at = 0
                if self._store.save(state):
                    return LifecycleAction(True, "recovered", state=state)
                continue

            for th in THRESHOLDS:
                if pct >= th and state.last_alert_pct < th:
                    if now - state.last_alert_at >= ALERT_COOLDOWN_SEC or state.last_alert_pct < th:
                        msg = f"Credits usage {th}% (available={available}, baseline={baseline})"
                        _notify(tid, f"threshold_{th}", msg, {"pct": th, "available": available})
                        state.last_alert_pct = th
                        state.last_alert_at = now
                        state.phase = "warning"
                        state.alerts_sent.append(f"{th}@{int(now)}")
                        if self._store.save(state):
                            return LifecycleAction(True, "alert", detail=msg, state=state)
                        break
            else:
                if self._store.save(state):
                    return LifecycleAction(True, "none", state=state)
            continue
        return LifecycleAction(False, "concurrency_conflict")

    def on_rating_failure(self, tenant_id: str, reason: str) -> LifecycleAction:
        if "insufficient" not in (reason or ""):
            return LifecycleAction(True, "none", detail=reason)
        state = self._store.get(str(tenant_id))
        if state.suspended:
            return LifecycleAction(True, "already_suspended", state=state)
        act = self._grace_or_suspend(str(tenant_id), state, reason=reason, now=time.time())
        self._store.save(state)
        return act

    def _grace_or_suspend(self, tid: str, state: TenantBalanceState, reason: str, now: float) -> LifecycleAction:
        if state.grace_until <= 0:
            state.phase = "grace"
            state.grace_started_at = now
            state.grace_until = now + GRACE_SEC
            state.last_grace_warn_at = now
            _notify(tid, "grace_started", f"Grace {GRACE_SEC}s — {reason}", {"grace_sec": GRACE_SEC})
            return LifecycleAction(True, "enter_grace", detail=reason, state=state)

        if now < state.grace_until:
            if now - state.last_grace_warn_at >= GRACE_WARN_EVERY_SEC:
                left = int(state.grace_until - now)
                _notify(tid, "grace_warning", f"Grace remaining ~{left}s", {"left_sec": left})
                state.last_grace_warn_at = now
                state.last_alert_at = now
            state.phase = "grace"
            return LifecycleAction(True, "in_grace", detail=reason, state=state)

        return self._do_suspend(tid, state, reason=f"grace_expired:{reason}")

    def _do_suspend(self, tid: str, state: TenantBalanceState, reason: str) -> LifecycleAction:
        if state.suspended:
            return LifecycleAction(True, "already_suspended", state=state)
        snap = _snapshot_and_stop(tid)
        state.snapshot = {
            "at": time.time(),
            "bots": snap.get("bots") or [],
            "stopped": snap.get("stopped"),
            "reason": reason,
        }
        state.suspended = True
        state.phase = "suspended"
        state.suspended_at = time.time()
        state.suspend_reason = reason[:300]
        _notify(
            tid,
            "suspended",
            f"Service suspended — {reason}; bots_stopped={snap.get('stopped')}",
            {"snapshot": state.snapshot},
        )
        return LifecycleAction(True, "suspend", detail=json.dumps(snap)[:300], state=state)

    def suspend(self, tenant_id: str, *, reason: str = "balance") -> LifecycleAction:
        state = self._store.get(str(tenant_id))
        act = self._do_suspend(str(tenant_id), state, reason=reason)
        self._store.save(state)
        return act

    def clear_suspension_on_credit(self, tenant_id: str) -> LifecycleAction:
        state = self._store.get(str(tenant_id))
        try:
            w = self._credits.get_wallet(str(tenant_id))
            if int(w.available) <= 0 and int(w.current_balance) <= 0:
                return LifecycleAction(True, "still_empty", state=state)
            state.baseline_credits = max(state.baseline_credits, int(w.current_balance))
        except Exception:
            pass
        state.suspended = False
        state.phase = "active"
        state.suspended_at = 0
        state.suspend_reason = ""
        state.grace_until = 0
        state.grace_started_at = 0
        state.last_alert_pct = 0
        state.last_grace_warn_at = 0
        self._store.save(state)
        _notify(str(tenant_id), "unsuspended", "Balance restored — suspension cleared")
        return LifecycleAction(True, "unsuspended", state=state)

    def is_hosting_allowed(self, tenant_id: str) -> tuple[bool, str]:
        state = self._store.get(str(tenant_id))
        if state.suspended or state.phase == "suspended":
            return False, "suspended_due_to_balance"
        w = self._credits.get_wallet(str(tenant_id))
        if int(w.available) <= 0:
            if state.grace_until > time.time():
                return True, "in_grace"
            return False, "insufficient_balance"
        return True, "ok"

    def tick(self, tenant_ids: list[str] | None = None) -> dict[str, Any]:
        ids = tenant_ids or []
        if not ids:
            try:
                ids = self._store.list_tenant_ids()
            except Exception:
                ids = []
        actions = []
        for tid in ids:
            try:
                st = self._store.get(tid)
                if st.phase in {"grace", "warning", "suspended"} or st.grace_until > 0:
                    act = self.on_balance_changed(tid)
                    if act.action not in {"none", "already_suspended"}:
                        actions.append({"tenant_id": tid, "action": act.action, "detail": act.detail})
            except Exception as exc:
                logger.debug("lifecycle tick %s: %s", tid, type(exc).__name__)
        return {"actions": actions, "checked": len(ids)}


_LC: BalanceLifecycle | None = None


def get_balance_lifecycle() -> BalanceLifecycle:
    global _LC
    if _LC is not None:
        return _LC
    from lumen.platform.credits import get_credit_service
    dsn = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    store: Any = PostgresLifecycleStore(dsn) if dsn else MemoryLifecycleStore()
    _LC = BalanceLifecycle(store, get_credit_service())
    return _LC


def reset_balance_lifecycle_for_tests() -> None:
    global _LC
    _LC = None
