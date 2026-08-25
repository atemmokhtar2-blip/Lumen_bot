"""Phase 2 usage batch ingest — telemetry only, no credit deduction."""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_BATCH_METRICS = 1_000_000_000  # hard cap per metric field


@dataclass
class UsageBatch:
    batch_id: str
    tenant_id: str
    bot_id: str
    window_start: float
    window_end: float
    messages_processed: int = 0
    llm_tokens_used: int = 0
    uptime_seconds: int = 0
    ram_mb: int = 0
    cpu_millicores: int = 0
    idempotency_key: str = ""
    status: str = "accepted"  # accepted | rated
    source: str = "api"  # api | supervisor | worker
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


@dataclass
class IngestResult:
    ok: bool
    reason: str = "ok"
    batch: Optional[UsageBatch] = None
    replay: bool = False


def _clamp_int(v: Any, default: int = 0) -> int:
    try:
        n = int(v)
    except Exception:
        return default
    if n < 0:
        return 0
    return min(n, MAX_BATCH_METRICS)


def validate_batch_payload(body: dict[str, Any]) -> tuple[Optional[dict], str]:
    if not isinstance(body, dict):
        return None, "body_must_be_object"
    bot_id = str(body.get("bot_id") or "").strip()[:120]
    if not bot_id:
        return None, "bot_id_required"
    key = str(body.get("idempotency_key") or "").strip()
    if len(key) < 8 or len(key) > 200:
        return None, "idempotency_key_invalid"
    try:
        ws = float(body.get("window_start") or 0)
        we = float(body.get("window_end") or 0)
    except Exception:
        return None, "window_invalid"
    if we < ws:
        return None, "window_end_before_start"
    if we - ws > 86400 * 7:
        return None, "window_too_large"
    return {
        "bot_id": bot_id,
        "window_start": ws,
        "window_end": we,
        "messages_processed": _clamp_int(body.get("messages_processed")),
        "llm_tokens_used": _clamp_int(body.get("llm_tokens_used")),
        "uptime_seconds": _clamp_int(body.get("uptime_seconds")),
        "ram_mb": _clamp_int(body.get("ram_mb")),
        "cpu_millicores": _clamp_int(body.get("cpu_millicores")),
        "idempotency_key": key,
        "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
    }, "ok"


class MemoryUsageBatchStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, UsageBatch] = {}
        self._idem: dict[str, str] = {}  # key -> batch_id
        self._order: list[str] = []

    def ingest(self, tenant_id: str, fields: dict[str, Any], *, source: str = "api") -> IngestResult:
        tid = str(tenant_id)
        key = fields["idempotency_key"]
        with self._lock:
            if key in self._idem:
                bid = self._idem[key]
                return IngestResult(ok=True, reason="idempotent_replay", batch=self._by_id[bid], replay=True)
            bid = f"ub_{uuid.uuid4().hex}"
            batch = UsageBatch(
                batch_id=bid,
                tenant_id=tid,
                bot_id=fields["bot_id"],
                window_start=float(fields["window_start"]),
                window_end=float(fields["window_end"]),
                messages_processed=int(fields["messages_processed"]),
                llm_tokens_used=int(fields["llm_tokens_used"]),
                uptime_seconds=int(fields["uptime_seconds"]),
                ram_mb=int(fields["ram_mb"]),
                cpu_millicores=int(fields["cpu_millicores"]),
                idempotency_key=key,
                status="accepted",
                source=source,
                metadata=dict(fields.get("metadata") or {}),
                created_at=time.time(),
            )
            self._by_id[bid] = batch
            self._idem[key] = bid
            self._order.append(bid)
            return IngestResult(ok=True, batch=batch)

    def list_for_tenant(self, tenant_id: str, *, limit: int = 50, status: str = "") -> list[UsageBatch]:
        with self._lock:
            rows = [self._by_id[i] for i in reversed(self._order) if self._by_id[i].tenant_id == str(tenant_id)]
            if status:
                rows = [r for r in rows if r.status == status]
            return rows[: int(limit)]

    def list_unrated(self, *, limit: int = 100) -> list[UsageBatch]:
        with self._lock:
            rows = [self._by_id[i] for i in self._order if self._by_id[i].status == "accepted"]
            return rows[: int(limit)]


_USAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_batches (
    batch_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    window_start DOUBLE PRECISION NOT NULL,
    window_end DOUBLE PRECISION NOT NULL,
    messages_processed BIGINT NOT NULL DEFAULT 0,
    llm_tokens_used BIGINT NOT NULL DEFAULT 0,
    uptime_seconds BIGINT NOT NULL DEFAULT 0,
    ram_mb BIGINT NOT NULL DEFAULT 0,
    cpu_millicores BIGINT NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'accepted',
    source TEXT NOT NULL DEFAULT 'api',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at DOUBLE PRECISION NOT NULL,
    CONSTRAINT usage_batches_idempotency UNIQUE (idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_usage_batches_tenant_time
    ON usage_batches (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_batches_status
    ON usage_batches (status, created_at ASC);
"""


class PostgresUsageBatchStore:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg import errors as pg_errors
        except ImportError as exc:
            raise RuntimeError("psycopg required") from exc
        self.dsn = dsn.strip()
        self._psycopg = psycopg
        self._dict_row = dict_row
        self._pg_errors = pg_errors
        with self._conn() as conn:
            conn.execute(_USAGE_SCHEMA)
            conn.commit()

    def _conn(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def _row(self, r: dict) -> UsageBatch:
        meta = r.get("metadata") or {}
        if isinstance(meta, str):
            import json
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return UsageBatch(
            batch_id=str(r["batch_id"]),
            tenant_id=str(r["tenant_id"]),
            bot_id=str(r["bot_id"]),
            window_start=float(r["window_start"]),
            window_end=float(r["window_end"]),
            messages_processed=int(r.get("messages_processed") or 0),
            llm_tokens_used=int(r.get("llm_tokens_used") or 0),
            uptime_seconds=int(r.get("uptime_seconds") or 0),
            ram_mb=int(r.get("ram_mb") or 0),
            cpu_millicores=int(r.get("cpu_millicores") or 0),
            idempotency_key=str(r.get("idempotency_key") or ""),
            status=str(r.get("status") or "accepted"),
            source=str(r.get("source") or "api"),
            metadata=dict(meta) if isinstance(meta, dict) else {},
            created_at=float(r.get("created_at") or 0),
        )

    def ingest(self, tenant_id: str, fields: dict[str, Any], *, source: str = "api") -> IngestResult:
        import json
        tid = str(tenant_id)
        key = fields["idempotency_key"]
        bid = f"ub_{uuid.uuid4().hex}"
        now = time.time()
        try:
            with self._conn() as conn:
                existing = conn.execute(
                    "SELECT * FROM usage_batches WHERE idempotency_key=%s", (key,)
                ).fetchone()
                if existing:
                    return IngestResult(ok=True, reason="idempotent_replay", batch=self._row(existing), replay=True)
                conn.execute(
                    """
                    INSERT INTO usage_batches (
                        batch_id, tenant_id, bot_id, window_start, window_end,
                        messages_processed, llm_tokens_used, uptime_seconds, ram_mb, cpu_millicores,
                        idempotency_key, status, source, metadata, created_at
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'accepted',%s,%s::jsonb,%s
                    )
                    """,
                    (
                        bid, tid, fields["bot_id"], fields["window_start"], fields["window_end"],
                        fields["messages_processed"], fields["llm_tokens_used"],
                        fields["uptime_seconds"], fields["ram_mb"], fields["cpu_millicores"],
                        key, source, json.dumps(fields.get("metadata") or {}), now,
                    ),
                )
                conn.commit()
        except self._pg_errors.UniqueViolation:
            with self._conn() as conn:
                existing = conn.execute(
                    "SELECT * FROM usage_batches WHERE idempotency_key=%s", (key,)
                ).fetchone()
                if existing:
                    return IngestResult(ok=True, reason="idempotent_replay", batch=self._row(existing), replay=True)
            raise
        batch = UsageBatch(
            batch_id=bid, tenant_id=tid, bot_id=fields["bot_id"],
            window_start=float(fields["window_start"]), window_end=float(fields["window_end"]),
            messages_processed=int(fields["messages_processed"]),
            llm_tokens_used=int(fields["llm_tokens_used"]),
            uptime_seconds=int(fields["uptime_seconds"]),
            ram_mb=int(fields["ram_mb"]), cpu_millicores=int(fields["cpu_millicores"]),
            idempotency_key=key, status="accepted", source=source,
            metadata=dict(fields.get("metadata") or {}), created_at=now,
        )
        return IngestResult(ok=True, batch=batch)

    def list_for_tenant(self, tenant_id: str, *, limit: int = 50, status: str = "") -> list[UsageBatch]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM usage_batches WHERE tenant_id=%s AND status=%s
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    (str(tenant_id), status, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM usage_batches WHERE tenant_id=%s
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    (str(tenant_id), int(limit)),
                ).fetchall()
        return [self._row(r) for r in rows]

    def list_unrated(self, *, limit: int = 100) -> list[UsageBatch]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM usage_batches WHERE status='accepted'
                ORDER BY created_at ASC LIMIT %s
                """,
                (int(limit),),
            ).fetchall()
        return [self._row(r) for r in rows]


class UsageBatchService:
    def __init__(self, store: Any) -> None:
        self._store = store

    def ingest(self, tenant_id: str, body: dict[str, Any], *, source: str = "api") -> IngestResult:
        fields, reason = validate_batch_payload(body)
        if not fields:
            return IngestResult(ok=False, reason=reason)
        return self._store.ingest(str(tenant_id), fields, source=source)

    def list_batches(self, tenant_id: str, *, limit: int = 50, status: str = "") -> list[UsageBatch]:
        return self._store.list_for_tenant(str(tenant_id), limit=limit, status=status)

    def list_unrated(self, *, limit: int = 100) -> list[UsageBatch]:
        return self._store.list_unrated(limit=limit)


_SVC: UsageBatchService | None = None


def get_usage_batch_service() -> UsageBatchService:
    global _SVC
    if _SVC is not None:
        return _SVC
    dsn = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL") or "").strip()
    if dsn:
        _SVC = UsageBatchService(PostgresUsageBatchStore(dsn))
    else:
        _SVC = UsageBatchService(MemoryUsageBatchStore())
    return _SVC


def reset_usage_batch_service_for_tests() -> None:
    global _SVC
    _SVC = None
