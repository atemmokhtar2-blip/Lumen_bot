"""Phase 2 usage batches — telemetry + sync credit rating (default ON).

Security / integrity:
- tenant_id only from auth layer (API) or trusted supervisor registry
- bot must be registered to tenant (unless TBE_USAGE_RELAX_OWNERSHIP=1 in dev)
- idempotency_key unique; content_hash of canonical metrics
- window: not future, not older than max age, max span 24h
- append-only table (PG trigger blocks UPDATE/DELETE)
- per-tenant rate limit on ingest
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_METRIC = 1_000_000_000
MAX_WINDOW_SEC = 86400
MAX_BATCH_AGE_SEC = int(os.getenv("TBE_USAGE_MAX_BATCH_AGE_SEC") or str(86400 * 2))
INGEST_RPM = int(os.getenv("TBE_USAGE_INGEST_RPM") or "60")


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
    content_hash: str = ""
    status: str = "accepted"
    source: str = "api"
    sequence: int = 0
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
    return min(n, MAX_METRIC)


def content_hash_for(fields: dict[str, Any]) -> str:
    canonical = {
        "bot_id": fields["bot_id"],
        "window_start": round(float(fields["window_start"]), 3),
        "window_end": round(float(fields["window_end"]), 3),
        "messages_processed": int(fields["messages_processed"]),
        "llm_tokens_used": int(fields["llm_tokens_used"]),
        "uptime_seconds": int(fields["uptime_seconds"]),
        "ram_mb": int(fields["ram_mb"]),
        "cpu_millicores": int(fields.get("cpu_millicores") or 0),
        "sequence": int(fields.get("sequence") or 0),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_batch_payload(body: dict[str, Any], *, now: float | None = None) -> tuple[Optional[dict], str]:
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
    if we <= ws:
        return None, "window_end_before_start"
    if we - ws > MAX_WINDOW_SEC:
        return None, "window_too_large"
    ts = float(now if now is not None else time.time())
    # allow 120s clock skew future
    if ws > ts + 120 or we > ts + 120:
        return None, "window_in_future"
    if ts - we > MAX_BATCH_AGE_SEC:
        return None, "window_too_stale"
    seq = _clamp_int(body.get("sequence"), 0)
    fields = {
        "bot_id": bot_id,
        "window_start": ws,
        "window_end": we,
        "messages_processed": _clamp_int(body.get("messages_processed")),
        "llm_tokens_used": _clamp_int(body.get("llm_tokens_used")),
        "uptime_seconds": _clamp_int(body.get("uptime_seconds")),
        "ram_mb": _clamp_int(body.get("ram_mb")),
        "cpu_millicores": _clamp_int(body.get("cpu_millicores")),
        "idempotency_key": key,
        "sequence": seq,
        "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
    }
    fields["content_hash"] = content_hash_for(fields)
    return fields, "ok"


# --- Bot ownership registry (tenant → bot_id) ---

class MemoryBotRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._owned: dict[str, set[str]] = {}  # tenant -> bot ids

    def register(self, tenant_id: str, bot_id: str) -> None:
        with self._lock:
            self._owned.setdefault(str(tenant_id), set()).add(str(bot_id)[:120])

    def is_owned(self, tenant_id: str, bot_id: str) -> bool:
        with self._lock:
            return str(bot_id)[:120] in self._owned.get(str(tenant_id), set())


_BOT_REG = MemoryBotRegistry()


def register_bot(tenant_id: str, bot_id: str) -> None:
    _BOT_REG.register(tenant_id, bot_id)
    dsn = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    if dsn:
        try:
            PostgresBotRegistry(dsn).register(tenant_id, bot_id)
        except Exception as exc:
            logger.warning("pg bot register failed: %s", type(exc).__name__)


def bot_owned(tenant_id: str, bot_id: str) -> bool:
    if _BOT_REG.is_owned(tenant_id, bot_id):
        return True
    dsn = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    if dsn:
        try:
            return PostgresBotRegistry(dsn).is_owned(tenant_id, bot_id)
        except Exception:
            return False
    return False


_PG_BOT_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_bot_registry (
    tenant_id TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tenant_id, bot_id)
);
"""


class PostgresBotRegistry:
    def __init__(self, dsn: str) -> None:
        import psycopg
        from psycopg.rows import dict_row
        self._psycopg = psycopg
        self._dict_row = dict_row
        self.dsn = dsn
        with self._conn() as conn:
            conn.execute(_PG_BOT_SCHEMA)
            conn.commit()

    def _conn(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def register(self, tenant_id: str, bot_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO usage_bot_registry (tenant_id, bot_id, created_at)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING
                """,
                (str(tenant_id), str(bot_id)[:120], time.time()),
            )
            conn.commit()

    def is_owned(self, tenant_id: str, bot_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM usage_bot_registry WHERE tenant_id=%s AND bot_id=%s",
                (str(tenant_id), str(bot_id)[:120]),
            ).fetchone()
        return bool(row)


def _rate_limit_ok(tenant_id: str) -> bool:
    if INGEST_RPM <= 0:
        return True
    try:
        from lumen.platform.rate_limit import get_rate_limiter
        return get_rate_limiter().allow(f"usage_batch:{tenant_id}", limit=INGEST_RPM, window_sec=60.0)
    except Exception:
        # fail-closed outside explicit dev/test
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        if env in {"dev", "development", "local", "test"}:
            return True
        return False


class MemoryUsageBatchStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, UsageBatch] = {}
        self._idem: dict[str, str] = {}
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
                cpu_millicores=int(fields.get("cpu_millicores") or 0),
                idempotency_key=key,
                content_hash=str(fields.get("content_hash") or ""),
                status="accepted",
                source=source,
                sequence=int(fields.get("sequence") or 0),
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
            return [self._by_id[i] for i in self._order if self._by_id[i].status == "accepted"][: int(limit)]


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
    content_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'accepted',
    source TEXT NOT NULL DEFAULT 'api',
    sequence BIGINT NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at DOUBLE PRECISION NOT NULL,
    CONSTRAINT usage_batches_idempotency UNIQUE (idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_usage_batches_tenant_time ON usage_batches (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_batches_status ON usage_batches (status, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_usage_batches_bot ON usage_batches (tenant_id, bot_id, window_end DESC);

CREATE OR REPLACE FUNCTION usage_batches_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'usage_batches_immutable: % not allowed', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_usage_batches_no_update ON usage_batches;
CREATE TRIGGER trg_usage_batches_no_update
  BEFORE UPDATE OR DELETE ON usage_batches
  FOR EACH ROW EXECUTE PROCEDURE usage_batches_immutable();
"""


class PostgresUsageBatchStore:
    def __init__(self, dsn: str) -> None:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg import errors as pg_errors
        self.dsn = dsn.strip()
        self._psycopg = psycopg
        self._dict_row = dict_row
        self._pg_errors = pg_errors
        with self._conn() as conn:
            try:
                conn.execute(_USAGE_SCHEMA)
            except Exception:
                for stmt in _USAGE_SCHEMA.split(";"):
                    s = stmt.strip()
                    if s:
                        try:
                            conn.execute(s)
                        except Exception:
                            pass
            conn.commit()

    def _conn(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def _row(self, r: dict) -> UsageBatch:
        meta = r.get("metadata") or {}
        if isinstance(meta, str):
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
            content_hash=str(r.get("content_hash") or ""),
            status=str(r.get("status") or "accepted"),
            source=str(r.get("source") or "api"),
            sequence=int(r.get("sequence") or 0),
            metadata=dict(meta) if isinstance(meta, dict) else {},
            created_at=float(r.get("created_at") or 0),
        )

    def ingest(self, tenant_id: str, fields: dict[str, Any], *, source: str = "api") -> IngestResult:
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
                        idempotency_key, content_hash, status, source, sequence, metadata, created_at
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'accepted',%s,%s,%s::jsonb,%s
                    )
                    """,
                    (
                        bid, tid, fields["bot_id"], fields["window_start"], fields["window_end"],
                        fields["messages_processed"], fields["llm_tokens_used"],
                        fields["uptime_seconds"], fields["ram_mb"], fields.get("cpu_millicores") or 0,
                        key, fields.get("content_hash") or "", source,
                        int(fields.get("sequence") or 0),
                        json.dumps(fields.get("metadata") or {}), now,
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
            ram_mb=int(fields["ram_mb"]),
            cpu_millicores=int(fields.get("cpu_millicores") or 0),
            idempotency_key=key, content_hash=str(fields.get("content_hash") or ""),
            status="accepted", source=source, sequence=int(fields.get("sequence") or 0),
            metadata=dict(fields.get("metadata") or {}), created_at=now,
        )
        return IngestResult(ok=True, batch=batch)

    def list_for_tenant(self, tenant_id: str, *, limit: int = 50, status: str = "") -> list[UsageBatch]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM usage_batches WHERE tenant_id=%s AND status=%s ORDER BY created_at DESC LIMIT %s",
                    (str(tenant_id), status, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM usage_batches WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s",
                    (str(tenant_id), int(limit)),
                ).fetchall()
        return [self._row(r) for r in rows]

    def list_unrated(self, *, limit: int = 100) -> list[UsageBatch]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM usage_batches WHERE status='accepted' ORDER BY created_at ASC LIMIT %s",
                (int(limit),),
            ).fetchall()
        return [self._row(r) for r in rows]


class UsageBatchService:
    def __init__(self, store: Any) -> None:
        self._store = store

    def ingest(
        self,
        tenant_id: str,
        body: dict[str, Any],
        *,
        source: str = "api",
        require_ownership: bool = True,
        skip_rate_limit: bool = False,
    ) -> IngestResult:
        fields, reason = validate_batch_payload(body)
        if not fields:
            return IngestResult(ok=False, reason=reason)
        relax = (os.getenv("TBE_USAGE_RELAX_OWNERSHIP") or "").strip().lower() in {
            "1", "true", "yes", "on",
        }
        if require_ownership and not relax:
            if not bot_owned(str(tenant_id), fields["bot_id"]):
                return IngestResult(ok=False, reason="bot_not_registered_for_tenant")
        if not skip_rate_limit and not _rate_limit_ok(str(tenant_id)):
            return IngestResult(ok=False, reason="rate_limited")
        result = self._store.ingest(str(tenant_id), fields, source=source)
        # ROOT FIX: connect telemetry → credits immediately (not only hourly scheduler)
        if result.ok and result.batch and not result.replay:
            sync = (os.getenv("TBE_USAGE_RATE_SYNC") or "1").strip().lower() not in {
                "0", "false", "no", "off",
            }
            if sync:
                try:
                    from lumen.platform.rating_engine import get_rating_engine
                    rated = get_rating_engine().rate_batch(result.batch)
                    if not rated.ok and "insufficient" in str(rated.reason or "").lower():
                        # Signal caller — batch accepted but unpaid
                        result.reason = f"accepted_unpaid:{rated.reason}"
                        try:
                            from lumen.platform.balance_lifecycle import get_balance_lifecycle
                            get_balance_lifecycle().on_balance_changed(str(tenant_id))
                        except Exception:
                            pass
                except Exception:
                    logger.debug("sync rate_batch after ingest failed", exc_info=True)
        return result

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
