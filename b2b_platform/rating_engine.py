"""Phase 3 — hardened rating & deduction.

Design:
- usage_batches stay immutable
- usage_ratings is append-only, UNIQUE(batch_id) → single rating
- debit ONLY via CreditService (prefer capture_reservation when holds exist)
- idempotency_key = rate-{batch_id} shared by debit + rating row
- insufficient funds → usage_rating_failures (retryable), not silent drop
- per-batch charge cap (TBE_RATING_MAX_CREDITS_PER_BATCH)
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_PER_BATCH = int(os.getenv("TBE_RATING_MAX_CREDITS_PER_BATCH") or "100000")


@dataclass
class CostBreakdown:
    messages: int = 0
    llm_tokens: int = 0
    uptime_seconds: int = 0
    ram_mb: int = 0
    message_credits: int = 0
    token_credits: int = 0
    host_credits: int = 0
    ram_credits: int = 0
    total_raw: int = 0
    total: int = 0  # after cap
    capped: bool = False


@dataclass
class RatingResult:
    ok: bool
    reason: str = "ok"
    batch_id: str = ""
    credits_charged: int = 0
    transaction_id: str = ""
    breakdown: Optional[CostBreakdown] = None
    skipped: bool = False
    used_capture: bool = False


def compute_batch_cost(batch: Any, credit_service: Any) -> CostBreakdown:
    bd = CostBreakdown()
    bd.messages = max(0, int(getattr(batch, "messages_processed", 0) or 0))
    bd.llm_tokens = max(0, int(getattr(batch, "llm_tokens_used", 0) or 0))
    bd.uptime_seconds = max(0, int(getattr(batch, "uptime_seconds", 0) or 0))
    bd.ram_mb = max(0, int(getattr(batch, "ram_mb", 0) or 0))

    bd.message_credits = int(credit_service.cost_for("telegram_message", bd.messages))
    bd.token_credits = int(credit_service.cost_for("llm_output_token", bd.llm_tokens))

    per_hour = int(credit_service.cost_for("hourly_hosting", 1))
    if per_hour > 0 and bd.uptime_seconds > 0:
        # pro-rate: ceil(seconds/3600 * per_hour)
        bd.host_credits = max(1, (bd.uptime_seconds * per_hour + 3599) // 3600)
    else:
        bd.host_credits = 0

    per_ram = int(credit_service.cost_for("docker_ram_mb_per_hour", 1))
    if per_ram > 0 and bd.ram_mb > 0 and bd.uptime_seconds > 0:
        # ram_mb * hours * rate, ceil
        num = bd.ram_mb * bd.uptime_seconds * per_ram
        bd.ram_credits = max(1, (num + 3599) // 3600)
    else:
        bd.ram_credits = 0

    bd.total_raw = int(bd.message_credits + bd.token_credits + bd.host_credits + bd.ram_credits)
    if MAX_PER_BATCH > 0 and bd.total_raw > MAX_PER_BATCH:
        bd.total = MAX_PER_BATCH
        bd.capped = True
    else:
        bd.total = bd.total_raw
    return bd


class MemoryRatingStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rated: dict[str, dict[str, Any]] = {}
        self._failures: dict[str, dict[str, Any]] = {}

    def is_rated(self, batch_id: str) -> bool:
        with self._lock:
            return str(batch_id) in self._rated

    def get_rating(self, batch_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return dict(self._rated[str(batch_id)]) if str(batch_id) in self._rated else None

    def try_begin_rating(self, batch_id: str, tenant_id: str, idempotency_key: str) -> tuple[bool, str]:
        """Claim batch for rating. Returns (claimed_new, reason)."""
        with self._lock:
            if str(batch_id) in self._rated:
                return False, "already_rated"
            # optimistic claim placeholder
            self._rated[str(batch_id)] = {
                "rating_id": f"rt_{uuid.uuid4().hex}",
                "batch_id": str(batch_id),
                "tenant_id": str(tenant_id),
                "credits_charged": -1,  # pending
                "transaction_id": "",
                "breakdown": {},
                "idempotency_key": idempotency_key,
                "status": "pending",
                "created_at": time.time(),
            }
            return True, "claimed"

    def finalize_rating(
        self,
        batch_id: str,
        *,
        credits_charged: int,
        transaction_id: str,
        breakdown: dict[str, Any],
        status: str = "rated",
    ) -> dict[str, Any]:
        with self._lock:
            row = self._rated.get(str(batch_id)) or {
                "rating_id": f"rt_{uuid.uuid4().hex}",
                "batch_id": str(batch_id),
                "idempotency_key": f"rate-{batch_id}",
            }
            row.update(
                {
                    "credits_charged": int(credits_charged),
                    "transaction_id": str(transaction_id),
                    "breakdown": dict(breakdown),
                    "status": status,
                    "finalized_at": time.time(),
                }
            )
            self._rated[str(batch_id)] = row
            self._failures.pop(str(batch_id), None)
            return row

    def abort_claim(self, batch_id: str) -> None:
        with self._lock:
            row = self._rated.get(str(batch_id))
            if row and row.get("status") == "pending" and int(row.get("credits_charged", 0)) < 0:
                del self._rated[str(batch_id)]

    def record_failure(self, batch_id: str, tenant_id: str, reason: str, breakdown: dict) -> None:
        with self._lock:
            self._failures[str(batch_id)] = {
                "batch_id": str(batch_id),
                "tenant_id": str(tenant_id),
                "reason": reason,
                "breakdown": breakdown,
                "updated_at": time.time(),
                "attempts": int(self._failures.get(str(batch_id), {}).get("attempts") or 0) + 1,
            }

    def list_failures(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._failures.values())
            rows.sort(key=lambda x: x.get("updated_at") or 0)
            return rows[: int(limit)]

    def list_ratings_for_tenant(self, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = [r for r in self._rated.values() if r.get("tenant_id") == str(tenant_id) and r.get("status") != "pending"]
            rows.sort(key=lambda x: x.get("finalized_at") or x.get("created_at") or 0, reverse=True)
            return rows[: int(limit)]


_RATING_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_ratings (
    rating_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    credits_charged BIGINT NOT NULL DEFAULT 0,
    transaction_id TEXT NOT NULL DEFAULT '',
    breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'rated',
    created_at DOUBLE PRECISION NOT NULL,
    finalized_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    CONSTRAINT usage_ratings_batch UNIQUE (batch_id),
    CONSTRAINT usage_ratings_idempotency UNIQUE (idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_usage_ratings_tenant ON usage_ratings (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS usage_rating_failures (
    batch_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempts INTEGER NOT NULL DEFAULT 1,
    updated_at DOUBLE PRECISION NOT NULL
);
"""


class PostgresRatingStore:
    def __init__(self, dsn: str) -> None:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg import errors as pg_errors
        self.dsn = dsn
        self._psycopg = psycopg
        self._dict_row = dict_row
        self._pg_errors = pg_errors
        with self._conn() as conn:
            conn.execute(_RATING_SCHEMA)
            conn.commit()

    def _conn(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def is_rated(self, batch_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM usage_ratings WHERE batch_id=%s AND status IN ('rated','zero')",
                (str(batch_id),),
            ).fetchone()
        return bool(row)

    def get_rating(self, batch_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM usage_ratings WHERE batch_id=%s", (str(batch_id),)
            ).fetchone()
        return dict(row) if row else None

    def try_begin_rating(self, batch_id: str, tenant_id: str, idempotency_key: str) -> tuple[bool, str]:
        import json
        rid = f"rt_{uuid.uuid4().hex}"
        now = time.time()
        try:
            with self._conn() as conn:
                existing = conn.execute(
                    "SELECT status FROM usage_ratings WHERE batch_id=%s", (str(batch_id),)
                ).fetchone()
                if existing and existing.get("status") in {"rated", "zero"}:
                    return False, "already_rated"
                if existing and existing.get("status") == "pending":
                    return False, "in_progress"
                conn.execute(
                    """
                    INSERT INTO usage_ratings
                    (rating_id, batch_id, tenant_id, credits_charged, transaction_id,
                     breakdown, idempotency_key, status, created_at)
                    VALUES (%s,%s,%s,-1,'',%s::jsonb,%s,'pending',%s)
                    """,
                    (rid, str(batch_id), str(tenant_id), json.dumps({}), idempotency_key, now),
                )
                conn.commit()
                return True, "claimed"
        except self._pg_errors.UniqueViolation:
            return False, "already_rated"

    def finalize_rating(self, batch_id, *, credits_charged, transaction_id, breakdown, status="rated"):
        import json
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE usage_ratings SET
                    credits_charged=%s, transaction_id=%s, breakdown=%s::jsonb,
                    status=%s, finalized_at=%s
                WHERE batch_id=%s
                """,
                (
                    int(credits_charged), str(transaction_id), json.dumps(breakdown),
                    status, time.time(), str(batch_id),
                ),
            )
            conn.execute("DELETE FROM usage_rating_failures WHERE batch_id=%s", (str(batch_id),))
            conn.commit()
            row = conn.execute(
                "SELECT * FROM usage_ratings WHERE batch_id=%s", (str(batch_id),)
            ).fetchone()
        return dict(row) if row else {}

    def abort_claim(self, batch_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM usage_ratings WHERE batch_id=%s AND status='pending'",
                (str(batch_id),),
            )
            conn.commit()

    def record_failure(self, batch_id, tenant_id, reason, breakdown):
        import json
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO usage_rating_failures (batch_id, tenant_id, reason, breakdown, attempts, updated_at)
                VALUES (%s,%s,%s,%s::jsonb,1,%s)
                ON CONFLICT (batch_id) DO UPDATE SET
                    reason=EXCLUDED.reason,
                    breakdown=EXCLUDED.breakdown,
                    attempts=usage_rating_failures.attempts+1,
                    updated_at=EXCLUDED.updated_at
                """,
                (str(batch_id), str(tenant_id), reason, json.dumps(breakdown), time.time()),
            )
            conn.commit()

    def list_failures(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM usage_rating_failures ORDER BY updated_at ASC LIMIT %s",
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_ratings_for_tenant(self, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM usage_ratings
                WHERE tenant_id=%s AND status IN ('rated','zero')
                ORDER BY COALESCE(finalized_at, created_at) DESC LIMIT %s
                """,
                (str(tenant_id), int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]


class RatingEngine:
    def __init__(self, rating_store: Any, usage_service: Any, credit_service: Any) -> None:
        self._ratings = rating_store
        self._usage = usage_service
        self._credits = credit_service

    def rate_batch(self, batch: Any) -> RatingResult:
        bid = str(getattr(batch, "batch_id", "") or "")
        tid = str(getattr(batch, "tenant_id", "") or "")
        if not bid or not tid:
            return RatingResult(ok=False, reason="invalid_batch")

        if self._ratings.is_rated(bid):
            return RatingResult(ok=True, reason="already_rated", batch_id=bid, skipped=True)

        idem = f"rate-{bid}"
        claimed, claim_reason = self._ratings.try_begin_rating(bid, tid, idem)
        if not claimed:
            return RatingResult(ok=True, reason=claim_reason, batch_id=bid, skipped=True)

        breakdown = compute_batch_cost(batch, self._credits)
        bd_dict = asdict(breakdown)

        if breakdown.total <= 0:
            self._ratings.finalize_rating(
                bid, credits_charged=0, transaction_id="", breakdown=bd_dict, status="zero"
            )
            return RatingResult(
                ok=True, reason="zero_cost", batch_id=bid, credits_charged=0,
                breakdown=breakdown, skipped=True,
            )

        # Prefer capturing existing reservation when enough hold exists
        wallet = self._credits.get_wallet(tid)
        used_capture = False
        if wallet.reserved_balance >= breakdown.total:
            debit = self._credits.capture_reservation(
                tid,
                breakdown.total,
                reason="usage_batch",
                reference_id=bid,
                idempotency_key=idem,
                metadata={"bot_id": getattr(batch, "bot_id", ""), "breakdown": bd_dict},
            )
            used_capture = bool(debit.ok)
        else:
            debit = self._credits.deduct_credits(
                tid,
                breakdown.total,
                reason="usage_batch",
                reference_id=bid,
                idempotency_key=idem,
                metadata={
                    "bot_id": getattr(batch, "bot_id", ""),
                    "content_hash": getattr(batch, "content_hash", ""),
                    "breakdown": bd_dict,
                    "capped": breakdown.capped,
                },
            )

        if not debit.ok:
            self._ratings.abort_claim(bid)
            self._ratings.record_failure(bid, tid, debit.reason, bd_dict)
            return RatingResult(
                ok=False, reason=debit.reason, batch_id=bid, breakdown=breakdown,
            )

        self._ratings.finalize_rating(
            bid,
            credits_charged=breakdown.total,
            transaction_id=debit.transaction_id or "",
            breakdown=bd_dict,
            status="rated",
        )
        return RatingResult(
            ok=True,
            batch_id=bid,
            credits_charged=breakdown.total,
            transaction_id=debit.transaction_id or "",
            breakdown=breakdown,
            used_capture=used_capture,
        )

    def rate_pending(self, *, limit: int = 50) -> dict[str, Any]:
        pending = self._usage.list_unrated(limit=limit)
        charged = 0
        failed = 0
        skipped = 0
        processed = 0
        captured = 0
        for batch in pending:
            if self._ratings.is_rated(batch.batch_id):
                skipped += 1
                continue
            r = self.rate_batch(batch)
            processed += 1
            if r.ok and r.skipped:
                skipped += 1
            elif r.ok:
                charged += int(r.credits_charged or 0)
                if r.used_capture:
                    captured += 1
            else:
                failed += 1
        return {
            "processed": processed,
            "charged_credits": charged,
            "failed": failed,
            "skipped": skipped,
            "captured": captured,
        }

    def list_failures(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._ratings.list_failures(limit=limit)

    def list_ratings(self, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._ratings.list_ratings_for_tenant(str(tenant_id), limit=limit)


def reserve_for_hosting(
    credit_service: Any,
    tenant_id: str,
    *,
    hours: int = 1,
    ram_mb: int = 256,
    reference_id: str = "",
    idempotency_key: str = "",
) -> Any:
    hours = max(1, int(hours))
    ram_mb = max(0, int(ram_mb))
    host = int(credit_service.cost_for("hourly_hosting", hours))
    ram = int(credit_service.cost_for("docker_ram_mb_per_hour", ram_mb * hours))
    amount = host + ram
    if amount <= 0:
        amount = 1
    key = idempotency_key or f"reserve-host-{tenant_id}-{reference_id or uuid.uuid4().hex[:12]}"
    return credit_service.reserve_credits(
        str(tenant_id), amount,
        reference_id=reference_id or "host_start",
        idempotency_key=key[:200],
    )


_ENGINE: RatingEngine | None = None


def get_rating_engine() -> RatingEngine:
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    from b2b_platform.usage_batches import get_usage_batch_service
    from b2b_platform.credits import get_credit_service
    dsn = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    store: Any = PostgresRatingStore(dsn) if dsn else MemoryRatingStore()
    _ENGINE = RatingEngine(store, get_usage_batch_service(), get_credit_service())
    return _ENGINE


def reset_rating_engine_for_tests() -> None:
    global _ENGINE
    _ENGINE = None
