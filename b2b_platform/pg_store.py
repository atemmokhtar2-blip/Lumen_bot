"""PostgreSQL-backed tenant store — production identity/billing source of truth.

Requires DATABASE_URL or POSTGRES_URL (psycopg v3).
Same behavioural surface as TenantStore / MongoUserStore.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Any

from .tenants import Tenant, _hash_key, _new_api_key

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    plan_id TEXT NOT NULL DEFAULT 'free',
    brand_name TEXT NOT NULL DEFAULT '',
    brand_logo_url TEXT NOT NULL DEFAULT '',
    primary_color TEXT NOT NULL DEFAULT '#2563eb',
    support_email TEXT NOT NULL DEFAULT '',
    custom_domain TEXT NOT NULL DEFAULT '',
    api_key_hash TEXT UNIQUE,
    api_key_prefix TEXT NOT NULL DEFAULT '',
    owner_telegram_id BIGINT NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DOUBLE PRECISION NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tenants_telegram ON tenants(owner_telegram_id);
CREATE INDEX IF NOT EXISTS idx_tenants_plan ON tenants(plan_id);
CREATE INDEX IF NOT EXISTS idx_tenants_api_hash ON tenants(api_key_hash);

CREATE TABLE IF NOT EXISTS metering (
    tenant_id TEXT NOT NULL,
    period TEXT NOT NULL,
    generations INTEGER NOT NULL DEFAULT 0,
    api_calls INTEGER NOT NULL DEFAULT 0,
    host_starts INTEGER NOT NULL DEFAULT 0,
    host_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
    bytes_out BIGINT NOT NULL DEFAULT 0,
    messages INTEGER NOT NULL DEFAULT 0,
    characters INTEGER NOT NULL DEFAULT 0,
    extra JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (tenant_id, period)
);
"""


def _database_url() -> str:
    return (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRESQL_URL")
        or ""
    ).strip()


class PostgresTenantStore:
    """Relational tenant registry (PostgreSQL)."""

    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for PostgreSQL tenants. pip install 'psycopg[binary]>=3.1'"
            ) from exc

        self.dsn = (dsn or _database_url()).strip()
        if not self.dsn:
            raise ValueError("DATABASE_URL or POSTGRES_URL is required for PostgresTenantStore")
        self._psycopg = psycopg
        self._dict_row = dict_row
        self._by_id: dict[str, Tenant] = {}  # billing._mutate compatibility
        self.index_path = None
        self._ensure_schema()
        logger.info("PostgresTenantStore ready")

    def _conn(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _row_to_tenant(self, row: dict[str, Any] | None) -> Tenant | None:
        if not row:
            return None
        meta = row.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return Tenant(
            tenant_id=str(row["tenant_id"]),
            name=str(row.get("name") or ""),
            plan_id=str(row.get("plan_id") or "free"),
            brand_name=str(row.get("brand_name") or ""),
            brand_logo_url=str(row.get("brand_logo_url") or ""),
            primary_color=str(row.get("primary_color") or "#2563eb"),
            support_email=str(row.get("support_email") or ""),
            custom_domain=str(row.get("custom_domain") or ""),
            api_key_hash=str(row.get("api_key_hash") or ""),
            api_key_prefix=str(row.get("api_key_prefix") or ""),
            owner_telegram_id=int(row.get("owner_telegram_id") or 0),
            active=bool(row.get("active", True)),
            created_at=float(row.get("created_at") or time.time()),
            metadata=dict(meta) if isinstance(meta, dict) else {},
        )

    def create(
        self,
        name: str,
        *,
        plan_id: str = "free",
        brand_name: str = "",
        owner_telegram_id: int = 0,
        **wl: Any,
    ) -> tuple[Tenant, str]:
        from .plans import normalize_plan_id

        tid = f"ten_{secrets.token_hex(8)}"
        raw = _new_api_key()
        t = Tenant(
            tenant_id=tid,
            name=(name or "User").strip()[:120],
            plan_id=normalize_plan_id(plan_id),
            brand_name=(brand_name or name or "").strip()[:120],
            brand_logo_url=str(wl.get("brand_logo_url") or "")[:300],
            primary_color=str(wl.get("primary_color") or "#2563eb")[:20],
            support_email=str(wl.get("support_email") or "")[:120],
            custom_domain=str(wl.get("custom_domain") or "")[:200],
            api_key_hash=_hash_key(raw),
            api_key_prefix=raw[:12],
            owner_telegram_id=int(owner_telegram_id or 0),
        )
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tenants (
                    tenant_id, name, plan_id, brand_name, brand_logo_url, primary_color,
                    support_email, custom_domain, api_key_hash, api_key_prefix,
                    owner_telegram_id, active, created_at, metadata, updated_at
                ) VALUES (
                    %(tenant_id)s, %(name)s, %(plan_id)s, %(brand_name)s, %(brand_logo_url)s,
                    %(primary_color)s, %(support_email)s, %(custom_domain)s, %(api_key_hash)s,
                    %(api_key_prefix)s, %(owner_telegram_id)s, %(active)s, %(created_at)s,
                    %(metadata)s::jsonb, %(updated_at)s
                )
                """,
                {
                    "tenant_id": t.tenant_id,
                    "name": t.name,
                    "plan_id": t.plan_id,
                    "brand_name": t.brand_name,
                    "brand_logo_url": t.brand_logo_url,
                    "primary_color": t.primary_color,
                    "support_email": t.support_email,
                    "custom_domain": t.custom_domain,
                    "api_key_hash": t.api_key_hash,
                    "api_key_prefix": t.api_key_prefix,
                    "owner_telegram_id": t.owner_telegram_id,
                    "active": t.active,
                    "created_at": t.created_at,
                    "metadata": json.dumps(t.metadata or {}),
                    "updated_at": time.time(),
                },
            )
            conn.commit()
        return t, raw

    def authenticate(self, api_key: str) -> Tenant | None:
        if not api_key:
            return None
        h = _hash_key(api_key)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tenants WHERE api_key_hash=%s AND active=TRUE LIMIT 1",
                (h,),
            ).fetchone()
        return self._row_to_tenant(row)

    def get(self, tenant_id: str) -> Tenant | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tenants WHERE tenant_id=%s LIMIT 1",
                (str(tenant_id),),
            ).fetchone()
        return self._row_to_tenant(row)

    def get_by_telegram(self, owner_telegram_id: int) -> Tenant | None:
        uid = int(owner_telegram_id or 0)
        if uid <= 0:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tenants WHERE owner_telegram_id=%s ORDER BY created_at ASC LIMIT 1",
                (uid,),
            ).fetchone()
        return self._row_to_tenant(row)

    def list_all(self) -> list[Tenant]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM tenants ORDER BY created_at ASC").fetchall()
        return [t for t in (self._row_to_tenant(r) for r in rows) if t]

    def set_plan(
        self,
        tenant_id: str,
        plan_id: str,
        *,
        metadata_updates: dict[str, Any] | None = None,
        active: bool = True,
    ) -> bool:
        from .plans import normalize_plan_id

        t = self.get(tenant_id)
        if not t:
            return False
        meta = dict(t.metadata or {})
        if metadata_updates:
            meta.update(metadata_updates)
        meta["last_plan_change"] = time.time()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE tenants SET plan_id=%s, active=%s, metadata=%s::jsonb, updated_at=%s
                WHERE tenant_id=%s
                """,
                (
                    normalize_plan_id(plan_id),
                    bool(active),
                    json.dumps(meta),
                    time.time(),
                    str(tenant_id),
                ),
            )
            conn.commit()
        return True

    def rotate_key(self, tenant_id: str) -> str | None:
        if not self.get(tenant_id):
            return None
        raw = _new_api_key()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE tenants SET api_key_hash=%s, api_key_prefix=%s, updated_at=%s
                WHERE tenant_id=%s
                """,
                (_hash_key(raw), raw[:12], time.time(), str(tenant_id)),
            )
            conn.commit()
        return raw

    def update_white_label(self, tenant_id: str, **fields: Any) -> Tenant | None:
        t = self.get(tenant_id)
        if not t:
            return None
        allowed = {
            "brand_name",
            "brand_logo_url",
            "primary_color",
            "support_email",
            "custom_domain",
            "name",
        }
        sets = []
        vals: list[Any] = []
        for k, v in fields.items():
            if k in allowed and v is not None:
                sets.append(f"{k}=%s")
                vals.append(str(v)[:300])
        if not sets:
            return t
        vals.extend([time.time(), str(tenant_id)])
        with self._conn() as conn:
            conn.execute(
                f"UPDATE tenants SET {', '.join(sets)}, updated_at=%s WHERE tenant_id=%s",
                vals,
            )
            conn.commit()
        return self.get(tenant_id)

    def _mutate(self, fn):
        """billing.apply_plan compatibility: load cache, run fn, persist."""
        self._by_id = {t.tenant_id: t for t in self.list_all()}
        result = fn()
        for tid, t in list(self._by_id.items()):
            with self._conn() as conn:
                conn.execute(
                    """
                    UPDATE tenants SET plan_id=%s, active=%s, metadata=%s::jsonb, updated_at=%s
                    WHERE tenant_id=%s
                    """,
                    (
                        t.plan_id,
                        bool(t.active),
                        json.dumps(t.metadata or {}),
                        time.time(),
                        tid,
                    ),
                )
                conn.commit()
        return result


class PostgresMeteringService:
    """Metering counters in PostgreSQL (atomic upserts)."""

    def __init__(self, dsn: str | None = None) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("psycopg required for PostgresMeteringService") from exc
        self.dsn = (dsn or _database_url()).strip()
        if not self.dsn:
            raise ValueError("DATABASE_URL required")
        self._psycopg = psycopg
        self._dict_row = dict_row
        # schema shared with tenant store
        PostgresTenantStore(self.dsn)

    def _conn(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def _period(self) -> str:
        return time.strftime("%Y-%m", time.gmtime())

    def snapshot(self, tenant_id: str) -> dict[str, Any]:
        period = self._period()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM metering WHERE tenant_id=%s AND period=%s",
                (str(tenant_id), period),
            ).fetchone()
        if not row:
            return {
                "tenant_id": str(tenant_id),
                "period": period,
                "generations": 0,
                "api_calls": 0,
                "host_starts": 0,
                "host_minutes": 0.0,
                "bytes_out": 0,
                "messages": 0,
                "characters": 0,
                "extra": {},
            }
        extra = row.get("extra") or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}
        return {
            "tenant_id": str(tenant_id),
            "period": period,
            "generations": int(row.get("generations") or 0),
            "api_calls": int(row.get("api_calls") or 0),
            "host_starts": int(row.get("host_starts") or 0),
            "host_minutes": float(row.get("host_minutes") or 0),
            "bytes_out": int(row.get("bytes_out") or 0),
            "messages": int(row.get("messages") or 0),
            "characters": int(row.get("characters") or 0),
            "extra": dict(extra) if isinstance(extra, dict) else {},
        }

    def record(
        self,
        tenant_id: str,
        *,
        generations: int = 0,
        api_calls: int = 0,
        host_starts: int = 0,
        host_minutes: float = 0.0,
        bytes_out: int = 0,
        messages: int = 0,
        characters: int = 0,
        event: str = "",
    ) -> Any:
        period = self._period()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO metering (
                    tenant_id, period, generations, api_calls, host_starts, host_minutes,
                    bytes_out, messages, characters, extra
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb
                )
                ON CONFLICT (tenant_id, period) DO UPDATE SET
                    generations = metering.generations + EXCLUDED.generations,
                    api_calls = metering.api_calls + EXCLUDED.api_calls,
                    host_starts = metering.host_starts + EXCLUDED.host_starts,
                    host_minutes = metering.host_minutes + EXCLUDED.host_minutes,
                    bytes_out = metering.bytes_out + EXCLUDED.bytes_out,
                    messages = metering.messages + EXCLUDED.messages,
                    characters = metering.characters + EXCLUDED.characters
                """,
                (
                    str(tenant_id),
                    period,
                    int(generations),
                    int(api_calls),
                    int(host_starts),
                    float(host_minutes),
                    int(bytes_out),
                    int(messages),
                    int(characters),
                ),
            )
            if event:
                conn.execute(
                    """
                    UPDATE metering SET extra = jsonb_set(
                        COALESCE(extra, '{}'::jsonb),
                        ARRAY[%s],
                        to_jsonb(COALESCE((extra->>%s)::int, 0) + 1)
                    )
                    WHERE tenant_id=%s AND period=%s
                    """,
                    (event[:64], event[:64], str(tenant_id), period),
                )
            conn.commit()
        from .metering import UsageBucket

        snap = self.snapshot(tenant_id)
        return UsageBucket(**{k: snap[k] for k in UsageBucket.__dataclass_fields__ if k in snap})

    def try_reserve_generation(self, tenant_id: str, limit: int) -> tuple[bool, str, int]:
        period = self._period()
        with self._conn() as conn:
            if limit > 0:
                row = conn.execute(
                    """
                    INSERT INTO metering (tenant_id, period, generations, extra)
                    VALUES (%s, %s, 1, '{}'::jsonb)
                    ON CONFLICT (tenant_id, period) DO UPDATE SET
                        generations = metering.generations + 1
                    WHERE metering.generations < %s
                    RETURNING generations
                    """,
                    (str(tenant_id), period, int(limit)),
                ).fetchone()
                conn.commit()
                if not row:
                    cur = self.snapshot(tenant_id)
                    return False, f"generation_quota_exceeded:{limit}", int(cur["generations"])
                return True, "ok", int(row["generations"])
            row = conn.execute(
                """
                INSERT INTO metering (tenant_id, period, generations, extra)
                VALUES (%s, %s, 1, '{}'::jsonb)
                ON CONFLICT (tenant_id, period) DO UPDATE SET
                    generations = metering.generations + 1
                RETURNING generations
                """,
                (str(tenant_id), period),
            ).fetchone()
            conn.commit()
            return True, "ok", int((row or {}).get("generations") or 1)

    def try_reserve_host_start(self, tenant_id: str, limit: int) -> tuple[bool, str, int]:
        period = self._period()
        with self._conn() as conn:
            row = conn.execute(
                """
                INSERT INTO metering (tenant_id, period, host_starts, extra)
                VALUES (%s, %s, 1, '{}'::jsonb)
                ON CONFLICT (tenant_id, period) DO UPDATE SET
                    host_starts = metering.host_starts + 1
                RETURNING host_starts
                """,
                (str(tenant_id), period),
            ).fetchone()
            conn.commit()
        return True, "ok", int((row or {}).get("host_starts") or 1)

    def check_rpm(self, tenant_id: str, limit: int) -> bool:
        from .rate_limit import get_rate_limiter

        return get_rate_limiter().allow(f"api:{tenant_id}", limit=limit, window_sec=60.0)
