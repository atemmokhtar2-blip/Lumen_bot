"""Phase 3 — Rating & deduction engine.

Rates accepted usage batches using CreditService pricing rules.
Never mutates usage_batches rows (append-only ratings table instead).
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CostBreakdown:
    messages: int = 0
    llm_tokens: int = 0
    uptime_hours: float = 0.0
    ram_mb_hours: float = 0.0
    message_credits: int = 0
    token_credits: int = 0
    host_credits: int = 0
    ram_credits: int = 0
    total: int = 0


@dataclass
class RatingResult:
    ok: bool
    reason: str = "ok"
    batch_id: str = ""
    credits_charged: int = 0
    transaction_id: str = ""
    breakdown: Optional[CostBreakdown] = None
    skipped: bool = False


def compute_batch_cost(batch: Any, credit_service: Any) -> CostBreakdown:
    """Map batch metrics → credits via pricing rules (integer only)."""
    bd = CostBreakdown()
    bd.messages = int(getattr(batch, "messages_processed", 0) or 0)
    bd.llm_tokens = int(getattr(batch, "llm_tokens_used", 0) or 0)
    uptime_s = int(getattr(batch, "uptime_seconds", 0) or 0)
    ram_mb = int(getattr(batch, "ram_mb", 0) or 0)
    # fractional hours quantized to milli-hours then cost
    bd.uptime_hours = uptime_s / 3600.0
    bd.ram_mb_hours = (ram_mb * uptime_s) / 3600.0 if ram_mb and uptime_s else 0.0

    bd.message_credits = int(credit_service.cost_for("telegram_message", bd.messages))
    # token pricing is per unit; large counts stay int
    bd.token_credits = int(credit_service.cost_for("llm_output_token", bd.llm_tokens))
    # host hour: ceil to at least 1 unit if any uptime in window with host activity
    host_units = 0
    if uptime_s > 0:
        # charge proportional: cost_per_hour * seconds/3600, rounded up to int credits
        per_hour = int(credit_service.cost_for("hourly_hosting", 1))
        host_units = max(1, (uptime_s * per_hour + 3599) // 3600) if per_hour else 0
    bd.host_credits = int(host_units)
    per_ram = int(credit_service.cost_for("docker_ram_mb_per_hour", 1))
    if per_ram and bd.ram_mb_hours > 0:
        bd.ram_credits = max(1, int(bd.ram_mb_hours * per_ram + 0.9999))
    else:
        bd.ram_credits = 0
    bd.total = int(bd.message_credits + bd.token_credits + bd.host_credits + bd.ram_credits)
    return bd


class MemoryRatingStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rated: dict[str, dict[str, Any]] = {}  # batch_id -> rating row

    def is_rated(self, batch_id: str) -> bool:
        with self._lock:
            return str(batch_id) in self._rated

    def record(
        self,
        *,
        batch_id: str,
        tenant_id: str,
        credits_charged: int,
        transaction_id: str,
        breakdown: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        with self._lock:
            if batch_id in self._rated:
                return self._rated[batch_id]
            row = {
                "rating_id": f"rt_{uuid.uuid4().hex}",
                "batch_id": str(batch_id),
                "tenant_id": str(tenant_id),
                "credits_charged": int(credits_charged),
                "transaction_id": str(transaction_id),
                "breakdown": dict(breakdown),
                "idempotency_key": idempotency_key,
                "created_at": time.time(),
            }
            self._rated[str(batch_id)] = row
            return row

    def list_rated_ids(self) -> set[str]:
        with self._lock:
            return set(self._rated.keys())


_RATING_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_ratings (
    rating_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    credits_charged BIGINT NOT NULL DEFAULT 0,
    transaction_id TEXT NOT NULL DEFAULT '',
    breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    CONSTRAINT usage_ratings_batch UNIQUE (batch_id),
    CONSTRAINT usage_ratings_idempotency UNIQUE (idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_usage_ratings_tenant ON usage_ratings (tenant_id, created_at DESC);
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
                "SELECT 1 FROM usage_ratings WHERE batch_id=%s", (str(batch_id),)
            ).fetchone()
        return bool(row)

    def record(self, *, batch_id, tenant_id, credits_charged, transaction_id, breakdown, idempotency_key):
        import json
        rid = f"rt_{uuid.uuid4().hex}"
        now = time.time()
        try:
            with self._conn() as conn:
                existing = conn.execute(
                    "SELECT * FROM usage_ratings WHERE batch_id=%s OR idempotency_key=%s",
                    (str(batch_id), idempotency_key),
                ).fetchone()
                if existing:
                    return dict(existing)
                conn.execute(
                    """
                    INSERT INTO usage_ratings
                    (rating_id, batch_id, tenant_id, credits_charged, transaction_id,
                     breakdown, idempotency_key, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                    """,
                    (
                        rid, str(batch_id), str(tenant_id), int(credits_charged),
                        str(transaction_id), json.dumps(breakdown), idempotency_key, now,
                    ),
                )
                conn.commit()
                return {
                    "rating_id": rid,
                    "batch_id": str(batch_id),
                    "tenant_id": str(tenant_id),
                    "credits_charged": int(credits_charged),
                    "transaction_id": str(transaction_id),
                    "breakdown": breakdown,
                    "idempotency_key": idempotency_key,
                    "created_at": now,
                }
        except self._pg_errors.UniqueViolation:
            with self._conn() as conn:
                existing = conn.execute(
                    "SELECT * FROM usage_ratings WHERE batch_id=%s", (str(batch_id),)
                ).fetchone()
            return dict(existing) if existing else {}


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

        breakdown = compute_batch_cost(batch, self._credits)
        idem = f"rate-{bid}"
        if breakdown.total <= 0:
            # zero-cost still record rating so batch is not reprocessed forever
            self._ratings.record(
                batch_id=bid, tenant_id=tid, credits_charged=0, transaction_id="",
                breakdown=breakdown.__dict__, idempotency_key=idem,
            )
            return RatingResult(
                ok=True, reason="zero_cost", batch_id=bid, credits_charged=0,
                breakdown=breakdown, skipped=True,
            )

        # Single debit gate
        debit = self._credits.deduct_credits(
            tid,
            breakdown.total,
            reason="usage_batch",
            reference_id=bid,
            idempotency_key=idem,
            metadata={
                "bot_id": getattr(batch, "bot_id", ""),
                "content_hash": getattr(batch, "content_hash", ""),
                "breakdown": breakdown.__dict__,
            },
        )
        if not debit.ok:
            return RatingResult(
                ok=False,
                reason=debit.reason,
                batch_id=bid,
                breakdown=breakdown,
            )
        self._ratings.record(
            batch_id=bid,
            tenant_id=tid,
            credits_charged=breakdown.total,
            transaction_id=debit.transaction_id or "",
            breakdown=breakdown.__dict__,
            idempotency_key=idem,
        )
        return RatingResult(
            ok=True,
            batch_id=bid,
            credits_charged=breakdown.total,
            transaction_id=debit.transaction_id or "",
            breakdown=breakdown,
        )

    def rate_pending(self, *, limit: int = 50) -> dict[str, Any]:
        pending = self._usage.list_unrated(limit=limit)
        # filter already rated (memory/pg)
        results = []
        charged = 0
        failed = 0
        skipped = 0
        for batch in pending:
            if self._ratings.is_rated(batch.batch_id):
                skipped += 1
                continue
            r = self.rate_batch(batch)
            results.append(r)
            if r.ok and not r.skipped and r.credits_charged:
                charged += r.credits_charged
            elif r.ok and r.skipped:
                skipped += 1
            elif not r.ok:
                failed += 1
        return {
            "processed": len(results),
            "charged_credits": charged,
            "failed": failed,
            "skipped": skipped,
        }


def reserve_for_hosting(
    credit_service: Any,
    tenant_id: str,
    *,
    hours: int = 1,
    ram_mb: int = 256,
    reference_id: str = "",
    idempotency_key: str = "",
) -> Any:
    """Pre-auth: reserve expected max hourly cost before host start."""
    host = int(credit_service.cost_for("hourly_hosting", max(1, int(hours))))
    ram = int(credit_service.cost_for("docker_ram_mb_per_hour", max(0, int(ram_mb) * max(1, int(hours)))))
    amount = host + ram
    if amount <= 0:
        amount = 1
    key = idempotency_key or f"reserve-host-{tenant_id}-{reference_id or uuid.uuid4().hex[:12]}"
    return credit_service.reserve_credits(
        str(tenant_id),
        amount,
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
    store: Any
    if dsn:
        store = PostgresRatingStore(dsn)
    else:
        store = MemoryRatingStore()
    _ENGINE = RatingEngine(store, get_usage_batch_service(), get_credit_service())
    return _ENGINE


def reset_rating_engine_for_tests() -> None:
    global _ENGINE
    _ENGINE = None
