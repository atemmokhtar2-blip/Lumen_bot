"""PostgreSQL credits store — production wallet + append-only ledger."""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .types import CreditResult, LedgerEntry, PricingRule, Wallet

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class PostgresCreditsStore:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("psycopg required for PostgresCreditsStore") from exc
        self.dsn = (dsn or "").strip()
        if not self.dsn:
            raise ValueError("DATABASE_URL required")
        self._psycopg = psycopg
        self._dict_row = dict_row
        self._ensure_schema()

    def _conn(self):
        return self._psycopg.connect(self.dsn, row_factory=self._dict_row)

    def _ensure_schema(self) -> None:
        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self._conn() as conn:
            conn.execute(sql)
            # seed pricing if empty
            n = conn.execute("SELECT COUNT(*) AS c FROM credit_pricing_rules").fetchone()
            if int((n or {}).get("c") or 0) == 0:
                seeds = [
                    ("docker_ram_mb_per_hour", 1, "RAM MB × hour"),
                    ("llm_output_token", 1, "per output token unit"),
                    ("telegram_message", 1, "per processed message"),
                    ("generation_cost", 50, "bot generation job"),
                    ("hourly_hosting", 10, "base host hour"),
                ]
                for rt, cost, desc in seeds:
                    conn.execute(
                        """
                        INSERT INTO credit_pricing_rules
                        (resource_type, cost_per_unit, is_active, version, description, updated_at)
                        VALUES (%s, %s, TRUE, 1, %s, %s)
                        ON CONFLICT (resource_type) DO NOTHING
                        """,
                        (rt, cost, desc, time.time()),
                    )
            conn.commit()

    def ensure_wallet(self, tenant_id: str) -> Wallet:
        tid = str(tenant_id)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO credit_wallets (tenant_id, current_balance, reserved_balance, currency, updated_at)
                VALUES (%s, 0, 0, 'credits', %s)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (tid, time.time()),
            )
            row = conn.execute(
                "SELECT * FROM credit_wallets WHERE tenant_id=%s",
                (tid,),
            ).fetchone()
            conn.commit()
        return self._row_wallet(row)

    def get_wallet(self, tenant_id: str) -> Wallet:
        return self.ensure_wallet(tenant_id)

    def _row_wallet(self, row: dict | None) -> Wallet:
        row = row or {}
        return Wallet(
            tenant_id=str(row.get("tenant_id") or ""),
            current_balance=int(row.get("current_balance") or 0),
            reserved_balance=int(row.get("reserved_balance") or 0),
            currency=str(row.get("currency") or "credits"),
            updated_at=float(row.get("updated_at") or 0),
        )

    def _row_entry(self, row: dict) -> LedgerEntry:
        meta = row.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return LedgerEntry(
            transaction_id=str(row["transaction_id"]),
            tenant_id=str(row["tenant_id"]),
            amount=int(row["amount"]),
            balance_after=int(row["balance_after"]),
            type=str(row["type"]),
            reference_id=str(row.get("reference_id") or ""),
            idempotency_key=str(row.get("idempotency_key") or ""),
            metadata=dict(meta) if isinstance(meta, dict) else {},
            created_at=float(row.get("created_at") or 0),
        )

    def credit(
        self,
        tenant_id: str,
        amount: int,
        *,
        type_: str = "purchase",
        reference_id: str = "",
        idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> CreditResult:
        if amount <= 0:
            return CreditResult(ok=False, reason="amount_must_be_positive")
        tid = str(tenant_id)
        key = idempotency_key or f"credit:{tid}:{uuid.uuid4().hex}"
        tx_id = f"tx_{uuid.uuid4().hex}"
        now = time.time()
        with self._conn() as conn:
            # idempotent replay
            existing = conn.execute(
                "SELECT * FROM credit_ledger WHERE idempotency_key=%s",
                (key,),
            ).fetchone()
            if existing:
                w = conn.execute(
                    "SELECT * FROM credit_wallets WHERE tenant_id=%s", (tid,)
                ).fetchone()
                e = self._row_entry(existing)
                return CreditResult(
                    ok=True, reason="idempotent_replay",
                    wallet=self._row_wallet(w), entry=e, transaction_id=e.transaction_id,
                )
            conn.execute(
                """
                INSERT INTO credit_wallets (tenant_id, current_balance, reserved_balance, currency, updated_at)
                VALUES (%s, 0, 0, 'credits', %s)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (tid, now),
            )
            row = conn.execute(
                "SELECT * FROM credit_wallets WHERE tenant_id=%s FOR UPDATE",
                (tid,),
            ).fetchone()
            bal = int(row["current_balance"]) + int(amount)
            conn.execute(
                """
                UPDATE credit_wallets
                SET current_balance=%s, updated_at=%s
                WHERE tenant_id=%s
                """,
                (bal, now, tid),
            )
            conn.execute(
                """
                INSERT INTO credit_ledger
                (transaction_id, tenant_id, amount, balance_after, type, reference_id,
                 idempotency_key, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    tx_id, tid, int(amount), bal, type_, reference_id or "",
                    key, json.dumps(metadata or {}), now,
                ),
            )
            conn.commit()
        w = self.get_wallet(tid)
        e = LedgerEntry(
            transaction_id=tx_id, tenant_id=tid, amount=int(amount),
            balance_after=bal, type=type_, reference_id=reference_id or "",
            idempotency_key=key, metadata=dict(metadata or {}), created_at=now,
        )
        return CreditResult(ok=True, wallet=w, entry=e, transaction_id=tx_id)

    def deduct(
        self,
        tenant_id: str,
        amount: int,
        *,
        type_: str = "generation_cost",
        reference_id: str = "",
        idempotency_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
        allow_from_reserved: bool = False,
    ) -> CreditResult:
        if amount <= 0:
            return CreditResult(ok=False, reason="amount_must_be_positive")
        tid = str(tenant_id)
        key = idempotency_key or f"deduct:{tid}:{uuid.uuid4().hex}"
        tx_id = f"tx_{uuid.uuid4().hex}"
        now = time.time()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM credit_ledger WHERE idempotency_key=%s",
                (key,),
            ).fetchone()
            if existing:
                w = conn.execute(
                    "SELECT * FROM credit_wallets WHERE tenant_id=%s", (tid,)
                ).fetchone()
                e = self._row_entry(existing)
                return CreditResult(
                    ok=True, reason="idempotent_replay",
                    wallet=self._row_wallet(w), entry=e, transaction_id=e.transaction_id,
                )
            conn.execute(
                """
                INSERT INTO credit_wallets (tenant_id, current_balance, reserved_balance, currency, updated_at)
                VALUES (%s, 0, 0, 'credits', %s)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (tid, now),
            )
            row = conn.execute(
                "SELECT * FROM credit_wallets WHERE tenant_id=%s FOR UPDATE",
                (tid,),
            ).fetchone()
            cur = int(row["current_balance"])
            reserved = int(row["reserved_balance"])
            available = cur - reserved
            if available < int(amount):
                conn.rollback()
                return CreditResult(
                    ok=False,
                    reason=f"insufficient_balance:{available}",
                    wallet=self._row_wallet(row),
                )
            # Conditional update (extra safety against races)
            updated = conn.execute(
                """
                UPDATE credit_wallets
                SET current_balance = current_balance - %s, updated_at = %s
                WHERE tenant_id = %s
                  AND (current_balance - reserved_balance) >= %s
                """,
                (int(amount), now, tid, int(amount)),
            )
            if updated.rowcount == 0:
                conn.rollback()
                w = self.get_wallet(tid)
                return CreditResult(ok=False, reason="insufficient_balance_race", wallet=w)
            bal = cur - int(amount)
            conn.execute(
                """
                INSERT INTO credit_ledger
                (transaction_id, tenant_id, amount, balance_after, type, reference_id,
                 idempotency_key, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    tx_id, tid, -int(amount), bal, type_, reference_id or "",
                    key, json.dumps(metadata or {}), now,
                ),
            )
            conn.commit()
        w = self.get_wallet(tid)
        e = LedgerEntry(
            transaction_id=tx_id, tenant_id=tid, amount=-int(amount),
            balance_after=bal, type=type_, reference_id=reference_id or "",
            idempotency_key=key, metadata=dict(metadata or {}), created_at=now,
        )
        return CreditResult(ok=True, wallet=w, entry=e, transaction_id=tx_id)

    def reserve(
        self,
        tenant_id: str,
        amount: int,
        *,
        reference_id: str = "",
        idempotency_key: str = "",
    ) -> CreditResult:
        if amount <= 0:
            return CreditResult(ok=False, reason="amount_must_be_positive")
        tid = str(tenant_id)
        key = idempotency_key or f"reserve:{tid}:{uuid.uuid4().hex}"
        tx_id = f"tx_{uuid.uuid4().hex}"
        now = time.time()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM credit_ledger WHERE idempotency_key=%s", (key,)
            ).fetchone()
            if existing:
                w = conn.execute(
                    "SELECT * FROM credit_wallets WHERE tenant_id=%s", (tid,)
                ).fetchone()
                e = self._row_entry(existing)
                return CreditResult(
                    ok=True, reason="idempotent_replay",
                    wallet=self._row_wallet(w), entry=e, transaction_id=e.transaction_id,
                )
            conn.execute(
                """
                INSERT INTO credit_wallets (tenant_id, current_balance, reserved_balance, currency, updated_at)
                VALUES (%s, 0, 0, 'credits', %s)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (tid, now),
            )
            row = conn.execute(
                "SELECT * FROM credit_wallets WHERE tenant_id=%s FOR UPDATE",
                (tid,),
            ).fetchone()
            available = int(row["current_balance"]) - int(row["reserved_balance"])
            if available < int(amount):
                conn.rollback()
                return CreditResult(
                    ok=False,
                    reason=f"insufficient_balance_for_reserve:{available}",
                    wallet=self._row_wallet(row),
                )
            conn.execute(
                """
                UPDATE credit_wallets
                SET reserved_balance = reserved_balance + %s, updated_at = %s
                WHERE tenant_id = %s
                """,
                (int(amount), now, tid),
            )
            bal = int(row["current_balance"])
            conn.execute(
                """
                INSERT INTO credit_ledger
                (transaction_id, tenant_id, amount, balance_after, type, reference_id,
                 idempotency_key, metadata, created_at)
                VALUES (%s, %s, 0, %s, 'reserve', %s, %s, %s::jsonb, %s)
                """,
                (tx_id, tid, bal, reference_id or "", key, json.dumps({"reserved": int(amount)}), now),
            )
            conn.commit()
        w = self.get_wallet(tid)
        e = LedgerEntry(
            transaction_id=tx_id, tenant_id=tid, amount=0, balance_after=bal,
            type="reserve", reference_id=reference_id or "", idempotency_key=key,
            metadata={"reserved": int(amount)}, created_at=now,
        )
        return CreditResult(ok=True, wallet=w, entry=e, transaction_id=tx_id)

    def release_reservation(
        self,
        tenant_id: str,
        amount: int,
        *,
        reference_id: str = "",
        idempotency_key: str = "",
    ) -> CreditResult:
        if amount <= 0:
            return CreditResult(ok=False, reason="amount_must_be_positive")
        tid = str(tenant_id)
        key = idempotency_key or f"release:{tid}:{uuid.uuid4().hex}"
        tx_id = f"tx_{uuid.uuid4().hex}"
        now = time.time()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM credit_ledger WHERE idempotency_key=%s", (key,)
            ).fetchone()
            if existing:
                w = conn.execute(
                    "SELECT * FROM credit_wallets WHERE tenant_id=%s", (tid,)
                ).fetchone()
                e = self._row_entry(existing)
                return CreditResult(
                    ok=True, reason="idempotent_replay",
                    wallet=self._row_wallet(w), entry=e, transaction_id=e.transaction_id,
                )
            row = conn.execute(
                "SELECT * FROM credit_wallets WHERE tenant_id=%s FOR UPDATE",
                (tid,),
            ).fetchone()
            if not row:
                conn.rollback()
                return CreditResult(ok=False, reason="wallet_not_found")
            release = min(int(amount), int(row["reserved_balance"]))
            conn.execute(
                """
                UPDATE credit_wallets
                SET reserved_balance = reserved_balance - %s, updated_at = %s
                WHERE tenant_id = %s
                """,
                (release, now, tid),
            )
            bal = int(row["current_balance"])
            conn.execute(
                """
                INSERT INTO credit_ledger
                (transaction_id, tenant_id, amount, balance_after, type, reference_id,
                 idempotency_key, metadata, created_at)
                VALUES (%s, %s, 0, %s, 'release_reservation', %s, %s, %s::jsonb, %s)
                """,
                (tx_id, tid, bal, reference_id or "", key, json.dumps({"released": release}), now),
            )
            conn.commit()
        w = self.get_wallet(tid)
        e = LedgerEntry(
            transaction_id=tx_id, tenant_id=tid, amount=0, balance_after=bal,
            type="release_reservation", reference_id=reference_id or "",
            idempotency_key=key, metadata={"released": release}, created_at=now,
        )
        return CreditResult(ok=True, wallet=w, entry=e, transaction_id=tx_id)

    def list_ledger(self, tenant_id: str, *, limit: int = 100) -> list[LedgerEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM credit_ledger
                WHERE tenant_id=%s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (str(tenant_id), int(limit)),
            ).fetchall()
        return [self._row_entry(r) for r in rows]

    def get_pricing(self, resource_type: str) -> Optional[PricingRule]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM credit_pricing_rules WHERE resource_type=%s AND is_active=TRUE",
                (str(resource_type),),
            ).fetchone()
        if not row:
            return None
        return PricingRule(
            resource_type=str(row["resource_type"]),
            cost_per_unit=int(row["cost_per_unit"]),
            is_active=bool(row["is_active"]),
            version=int(row.get("version") or 1),
            description=str(row.get("description") or ""),
        )

    def list_pricing(self) -> list[PricingRule]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM credit_pricing_rules WHERE is_active=TRUE ORDER BY resource_type"
            ).fetchall()
        return [
            PricingRule(
                resource_type=str(r["resource_type"]),
                cost_per_unit=int(r["cost_per_unit"]),
                is_active=bool(r["is_active"]),
                version=int(r.get("version") or 1),
                description=str(r.get("description") or ""),
            )
            for r in rows
        ]
