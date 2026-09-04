"""PostgreSQL double-entry credits store."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .accounts import (
    SYSTEM_HOLDS,
    SYSTEM_REVENUE,
    SYSTEM_TREASURY,
    user_wallet_account,
    validate_amount,
    validate_idempotency_key,
)
from .types import CreditResult, LedgerEntry, LedgerLeg, PricingRule, ReconcileReport, Wallet

logger = logging.getLogger(__name__)


def set_tenant_context(conn, tenant_id: str) -> None:
    """SET LOCAL app.tenant_id for PostgreSQL RLS (required non-empty)."""
    tid = str(tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id_required_for_rls")
    try:
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tid,))
        conn.execute("SELECT set_config('app.rls_bypass', %s, true)", ("off",))
    except Exception:
        try:
            cur = conn.cursor()
            cur.execute("SELECT set_config(%s, %s, true)", ("app.tenant_id", tid))
            cur.execute("SELECT set_config(%s, %s, true)", ("app.rls_bypass", "off"))
        except Exception:
            logger.debug("set_tenant_context failed", exc_info=True)
            raise


def set_rls_bypass(conn, enabled: bool = True) -> None:
    """Maintenance-only: allow schema ops without a tenant GUC. Never use for user requests."""
    flag = "on" if enabled else "off"
    try:
        conn.execute("SELECT set_config('app.rls_bypass', %s, true)", (flag,))
    except Exception:
        cur = conn.cursor()
        cur.execute("SELECT set_config(%s, %s, true)", ("app.rls_bypass", flag))
_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _hash_entry(prev: str, payload: dict) -> str:
    raw = prev + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class PostgresCreditsStore:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg import errors as pg_errors
        except ImportError as exc:
            raise RuntimeError("psycopg required") from exc
        self.dsn = (dsn or "").strip()
        if not self.dsn:
            raise ValueError("DATABASE_URL required")
        self._psycopg = psycopg
        self._dict_row = dict_row
        self._pg_errors = pg_errors
        self._ensure_schema()

    def _conn(self, tenant_id: str | None = None):
        """Open connection; when tenant_id given, set RLS GUC app.tenant_id."""
        conn = self._psycopg.connect(self.dsn, row_factory=self._dict_row)
        if tenant_id is not None and str(tenant_id).strip():
            set_tenant_context(conn, str(tenant_id))
        return conn

    def _tenant_conn(self, tenant_id: str):
        """Connection with app.tenant_id set for PostgreSQL RLS (fail-closed)."""
        from contextlib import contextmanager

        tid = str(tenant_id or "").strip()
        if not tid:
            raise ValueError("tenant_id_required_for_rls")

        @contextmanager
        def _cm():
            with self._conn(tid) as conn:
                yield conn

        return _cm()

    def _ensure_schema(self) -> None:
        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        # PG11-13: EXECUTE PROCEDURE; try whole schema and log trigger errors
        with self._conn() as conn:
            try:
                set_rls_bypass(conn, True)
            except Exception:
                pass
            try:
                conn.execute(sql)
            except Exception as exc:
                logger.warning("schema apply partial: %s", type(exc).__name__)
                # apply without triggers
                for stmt in sql.split(";"):
                    s = stmt.strip()
                    if not s or s.startswith("--"):
                        continue
                    try:
                        conn.execute(s)
                    except Exception:
                        pass
            self._seed(conn)
            conn.commit()

    def _ensure_promo_columns(self, conn) -> None:
        try:
            conn.execute(
                "ALTER TABLE credit_wallets ADD COLUMN IF NOT EXISTS promotional_balance BIGINT NOT NULL DEFAULT 0"
            )
            conn.execute(
                "ALTER TABLE credit_wallets ADD COLUMN IF NOT EXISTS promo_expires_at DOUBLE PRECISION NOT NULL DEFAULT 0"
            )
        except Exception:
            pass

    def _seed(self, conn) -> None:
        for acc, kind in [
            (SYSTEM_TREASURY, "system_treasury"),
            (SYSTEM_REVENUE, "system_revenue"),
            (SYSTEM_HOLDS, "system_holds"),
        ]:
            conn.execute(
                """
                INSERT INTO credit_accounts (account_id, kind, tenant_id, currency, created_at)
                VALUES (%s, %s, '', 'credits', %s)
                ON CONFLICT (account_id) DO NOTHING
                """,
                (acc, kind, time.time()),
            )
        n = conn.execute("SELECT COUNT(*) AS c FROM credit_pricing_rules").fetchone()
        if int((n or {}).get("c") or 0) == 0:
            for rt, cost, desc in [
                ("docker_ram_mb_per_hour", 1, "RAM MB × hour"),
                ("llm_output_token", 1, "token unit"),
                ("llm_prompt_1k", 1, "per 1k prompt tokens"),
                ("llm_completion_1k", 3, "per 1k completion tokens"),
                ("telegram_message", 1, "message"),
                ("generation_cost", 50, "generation"),
                ("hourly_hosting", 10, "host hour"),
            ]:
                conn.execute(
                    """
                    INSERT INTO credit_pricing_rules
                    (resource_type, cost_per_unit, is_active, version, description, updated_at)
                    VALUES (%s,%s,TRUE,1,%s,%s) ON CONFLICT DO NOTHING
                    """,
                    (rt, cost, desc, time.time()),
                )

    def ensure_wallet(self, tenant_id: str) -> Wallet:
        tid = str(tenant_id)
        aid = user_wallet_account(tid)
        now = time.time()
        with self._tenant_conn(tid) as conn:
            self._ensure_promo_columns(conn)
            conn.execute(
                """
                INSERT INTO credit_accounts (account_id, kind, tenant_id, currency, created_at)
                VALUES (%s, 'user_wallet', %s, 'credits', %s)
                ON CONFLICT (account_id) DO NOTHING
                """,
                (aid, tid, now),
            )
            conn.execute(
                """
                INSERT INTO credit_wallets (tenant_id, account_id, current_balance, reserved_balance, currency, updated_at)
                VALUES (%s, %s, 0, 0, 'credits', %s)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (tid, aid, now),
            )
            row = conn.execute(
                "SELECT * FROM credit_wallets WHERE tenant_id=%s", (tid,)
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
            account_id=str(row.get("account_id") or ""),
            promotional_balance=int(row.get("promotional_balance") or 0),
            promo_expires_at=float(row.get("promo_expires_at") or 0),
        )

    def _fetch_idem(self, conn, key: str, tid: str) -> Optional[CreditResult]:
        tx = conn.execute(
            "SELECT * FROM credit_transactions WHERE idempotency_key=%s", (key,)
        ).fetchone()
        if not tx:
            return None
        legs_rows = conn.execute(
            "SELECT * FROM credit_legs WHERE transaction_id=%s", (tx["transaction_id"],)
        ).fetchall()
        legs = [
            LedgerLeg(str(r["account_id"]), str(r["side"]), int(r["amount"]))
            for r in legs_rows
        ]
        w = conn.execute(
            "SELECT * FROM credit_wallets WHERE tenant_id=%s", (tid,)
        ).fetchone()
        meta = tx.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        e = LedgerEntry(
            transaction_id=str(tx["transaction_id"]),
            tenant_id=str(tx.get("tenant_id") or tid),
            type=str(tx["type"]),
            legs=legs,
            balance_after=int(self._row_wallet(w).current_balance),
            reserved_after=int(self._row_wallet(w).reserved_balance),
            reference_id=str(tx.get("reference_id") or ""),
            idempotency_key=str(tx.get("idempotency_key") or ""),
            prev_hash=str(tx.get("prev_hash") or ""),
            entry_hash=str(tx.get("entry_hash") or ""),
            metadata=dict(meta) if isinstance(meta, dict) else {},
            created_at=float(tx.get("created_at") or 0),
        )
        return CreditResult(
            ok=True, reason="idempotent_replay",
            wallet=self._row_wallet(w), entry=e, transaction_id=e.transaction_id,
        )

    def _last_hash(self, conn) -> str:
        row = conn.execute(
            "SELECT entry_hash FROM credit_transactions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return str((row or {}).get("entry_hash") or "")

    def _write_tx(
        self, conn, *, tid, type_, legs, reference_id, key, metadata, bal, reserved, now
    ) -> tuple[str, str, str]:
        tx_id = f"tx_{uuid.uuid4().hex}"
        prev = self._last_hash(conn)
        payload = {
            "transaction_id": tx_id,
            "tenant_id": tid,
            "type": type_,
            "legs": [{"a": x.account_id, "s": x.side, "n": x.amount} for x in legs],
            "idempotency_key": key,
            "created_at": now,
        }
        h = _hash_entry(prev, payload)
        conn.execute(
            """
            INSERT INTO credit_transactions
            (transaction_id, tenant_id, type, reference_id, idempotency_key, metadata,
             prev_hash, entry_hash, created_at)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
            """,
            (
                tx_id, tid, type_, reference_id or "", key,
                json.dumps(metadata or {}), prev, h, now,
            ),
        )
        for leg in legs:
            # ensure account exists for hold:tenant
            conn.execute(
                """
                INSERT INTO credit_accounts (account_id, kind, tenant_id, currency, created_at)
                VALUES (%s, %s, %s, 'credits', %s)
                ON CONFLICT (account_id) DO NOTHING
                """,
                (
                    leg.account_id,
                    "user_hold" if leg.account_id.startswith("hold:") else "system",
                    tid if leg.account_id.startswith(("wallet:", "hold:")) else "",
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO credit_legs (transaction_id, account_id, side, amount, created_at)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (tx_id, leg.account_id, leg.side, int(leg.amount), now),
            )
        return tx_id, prev, h

    def credit(self, tenant_id, amount, *, type_="purchase", reference_id="",
               idempotency_key="", metadata=None,
               promotional: bool = False, promo_expires_at: float = 0.0) -> CreditResult:
        err = validate_amount(amount)
        if err:
            return CreditResult(ok=False, reason=err)
        tid = str(tenant_id)
        key = idempotency_key or f"credit:{tid}:{uuid.uuid4().hex}"
        err = validate_idempotency_key(key)
        if err:
            return CreditResult(ok=False, reason=err)
        self.ensure_wallet(tid)
        now = time.time()
        try:
            with self._tenant_conn(tid) as conn:
                hit = self._fetch_idem(conn, key, tid)
                if hit:
                    return hit
                row = conn.execute(
                    "SELECT * FROM credit_wallets WHERE tenant_id=%s FOR UPDATE", (tid,)
                ).fetchone()
                bal = int(row["current_balance"]) + int(amount)
                reserved = int(row["reserved_balance"])
                promo = int(row.get("promotional_balance") or 0)
                promo_exp = float(row.get("promo_expires_at") or 0)
                if promotional:
                    promo = promo + int(amount)
                    if promo_expires_at and float(promo_expires_at) > 0:
                        if not promo_exp or float(promo_expires_at) < promo_exp:
                            promo_exp = float(promo_expires_at)
                conn.execute(
                    "UPDATE credit_wallets SET current_balance=%s, promotional_balance=%s, "
                    "promo_expires_at=%s, updated_at=%s WHERE tenant_id=%s",
                    (bal, promo, promo_exp, now, tid),
                )
                wa = user_wallet_account(tid)
                legs = [
                    LedgerLeg(SYSTEM_TREASURY, "debit", int(amount)),
                    LedgerLeg(wa, "credit", int(amount)),
                ]
                tx_id, prev, h = self._write_tx(
                    conn, tid=tid, type_=type_, legs=legs, reference_id=reference_id,
                    key=key, metadata=metadata, bal=bal, reserved=reserved, now=now,
                )
                conn.commit()
        except self._pg_errors.UniqueViolation:
            with self._tenant_conn(tid) as conn:
                hit = self._fetch_idem(conn, key, tid)
                if hit:
                    return hit
            raise
        w = self.get_wallet(tid)
        e = LedgerEntry(
            transaction_id=tx_id, tenant_id=tid, type=type_, legs=legs,
            balance_after=bal, reserved_after=reserved, reference_id=reference_id or "",
            idempotency_key=key, prev_hash=prev, entry_hash=h,
            metadata=dict(metadata or {}), created_at=now,
        )
        return CreditResult(ok=True, wallet=w, entry=e, transaction_id=tx_id)

    def deduct(self, tenant_id, amount, *, type_="generation_cost", reference_id="",
               idempotency_key="", metadata=None, allow_from_reserved=False) -> CreditResult:
        err = validate_amount(amount)
        if err:
            return CreditResult(ok=False, reason=err)
        tid = str(tenant_id)
        key = idempotency_key or f"deduct:{tid}:{uuid.uuid4().hex}"
        err = validate_idempotency_key(key)
        if err:
            return CreditResult(ok=False, reason=err)
        self.ensure_wallet(tid)
        now = time.time()
        try:
            with self._tenant_conn(tid) as conn:
                hit = self._fetch_idem(conn, key, tid)
                if hit:
                    return hit
                row = conn.execute(
                    "SELECT * FROM credit_wallets WHERE tenant_id=%s FOR UPDATE", (tid,)
                ).fetchone()
                cur = int(row["current_balance"])
                reserved = int(row["reserved_balance"])
                if cur - reserved < int(amount):
                    conn.rollback()
                    return CreditResult(
                        ok=False, reason=f"insufficient_balance:{cur - reserved}",
                        wallet=self._row_wallet(row),
                    )
                promo = int(row.get("promotional_balance") or 0)
                promo_take = min(promo, int(amount))
                new_promo = promo - promo_take
                upd = conn.execute(
                    """
                    UPDATE credit_wallets
                    SET current_balance = current_balance - %s,
                        promotional_balance = %s,
                        updated_at=%s
                    WHERE tenant_id=%s AND (current_balance - reserved_balance) >= %s
                    """,
                    (int(amount), new_promo, now, tid, int(amount)),
                )
                if upd.rowcount == 0:
                    conn.rollback()
                    return CreditResult(ok=False, reason="insufficient_balance_race", wallet=self.get_wallet(tid))
                bal = cur - int(amount)
                wa = user_wallet_account(tid)
                legs = [
                    LedgerLeg(wa, "debit", int(amount)),
                    LedgerLeg(SYSTEM_REVENUE, "credit", int(amount)),
                ]
                tx_id, prev, h = self._write_tx(
                    conn, tid=tid, type_=type_, legs=legs, reference_id=reference_id,
                    key=key, metadata=metadata, bal=bal, reserved=reserved, now=now,
                )
                conn.commit()
        except self._pg_errors.UniqueViolation:
            with self._tenant_conn(tid) as conn:
                hit = self._fetch_idem(conn, key, tid)
                if hit:
                    return hit
            raise
        w = self.get_wallet(tid)
        e = LedgerEntry(
            transaction_id=tx_id, tenant_id=tid, type=type_, legs=legs,
            balance_after=bal, reserved_after=reserved, reference_id=reference_id or "",
            idempotency_key=key, prev_hash=prev, entry_hash=h,
            metadata=dict(metadata or {}), created_at=now,
        )
        return CreditResult(ok=True, wallet=w, entry=e, transaction_id=tx_id)

    def reserve(self, tenant_id, amount, *, reference_id="", idempotency_key="") -> CreditResult:
        err = validate_amount(amount)
        if err:
            return CreditResult(ok=False, reason=err)
        tid = str(tenant_id)
        key = idempotency_key or f"reserve:{tid}:{uuid.uuid4().hex}"
        err = validate_idempotency_key(key)
        if err:
            return CreditResult(ok=False, reason=err)
        self.ensure_wallet(tid)
        now = time.time()
        try:
            with self._tenant_conn(tid) as conn:
                hit = self._fetch_idem(conn, key, tid)
                if hit:
                    return hit
                row = conn.execute(
                    "SELECT * FROM credit_wallets WHERE tenant_id=%s FOR UPDATE", (tid,)
                ).fetchone()
                # Burn expired promotional under the same FOR UPDATE lock
                promo = int(row.get("promotional_balance") or 0)
                exp = float(row.get("promo_expires_at") or 0)
                if promo > 0 and exp > 0 and now >= exp:
                    burn = min(promo, int(row["current_balance"]))
                    if burn > 0:
                        conn.execute(
                            """
                            UPDATE credit_wallets
                            SET current_balance = current_balance - %s,
                                promotional_balance = 0, promo_expires_at = 0, updated_at=%s
                            WHERE tenant_id=%s
                            """,
                            (burn, now, tid),
                        )
                        row = dict(row)
                        row["current_balance"] = int(row["current_balance"]) - burn
                        row["promotional_balance"] = 0
                        row["promo_expires_at"] = 0
                avail = int(row["current_balance"]) - int(row["reserved_balance"])
                if avail < int(amount):
                    conn.rollback()
                    return CreditResult(
                        ok=False, reason=f"insufficient_balance_for_reserve:{avail}",
                        wallet=self._row_wallet(row),
                    )
                conn.execute(
                    """
                    UPDATE credit_wallets SET reserved_balance = reserved_balance + %s, updated_at=%s
                    WHERE tenant_id=%s
                    """,
                    (int(amount), now, tid),
                )
                bal = int(row["current_balance"])
                reserved = int(row["reserved_balance"]) + int(amount)
                legs = [
                    LedgerLeg(f"hold:{tid}", "debit", int(amount)),
                    LedgerLeg(SYSTEM_HOLDS, "credit", int(amount)),
                ]
                tx_id, prev, h = self._write_tx(
                    conn, tid=tid, type_="reserve", legs=legs, reference_id=reference_id,
                    key=key, metadata={"reserved": int(amount)}, bal=bal, reserved=reserved, now=now,
                )
                conn.commit()
        except self._pg_errors.UniqueViolation:
            with self._tenant_conn(tid) as conn:
                hit = self._fetch_idem(conn, key, tid)
                if hit:
                    return hit
            raise
        w = self.get_wallet(tid)
        e = LedgerEntry(
            transaction_id=tx_id, tenant_id=tid, type="reserve", legs=legs,
            balance_after=bal, reserved_after=reserved, reference_id=reference_id or "",
            idempotency_key=key, prev_hash=prev, entry_hash=h,
            metadata={"reserved": int(amount)}, created_at=now,
        )
        return CreditResult(ok=True, wallet=w, entry=e, transaction_id=tx_id)

    def release_reservation(self, tenant_id, amount, *, reference_id="",
                            idempotency_key="") -> CreditResult:
        err = validate_amount(amount)
        if err:
            return CreditResult(ok=False, reason=err)
        tid = str(tenant_id)
        key = idempotency_key or f"release:{tid}:{uuid.uuid4().hex}"
        err = validate_idempotency_key(key)
        if err:
            return CreditResult(ok=False, reason=err)
        now = time.time()
        try:
            with self._tenant_conn(tid) as conn:
                hit = self._fetch_idem(conn, key, tid)
                if hit:
                    return hit
                row = conn.execute(
                    "SELECT * FROM credit_wallets WHERE tenant_id=%s FOR UPDATE", (tid,)
                ).fetchone()
                if not row:
                    return CreditResult(ok=False, reason="wallet_not_found")
                release = min(int(amount), int(row["reserved_balance"]))
                if release <= 0:
                    return CreditResult(ok=False, reason="nothing_reserved", wallet=self._row_wallet(row))
                conn.execute(
                    """
                    UPDATE credit_wallets SET reserved_balance = reserved_balance - %s, updated_at=%s
                    WHERE tenant_id=%s
                    """,
                    (release, now, tid),
                )
                bal = int(row["current_balance"])
                reserved = int(row["reserved_balance"]) - release
                legs = [
                    LedgerLeg(SYSTEM_HOLDS, "debit", release),
                    LedgerLeg(f"hold:{tid}", "credit", release),
                ]
                tx_id, prev, h = self._write_tx(
                    conn, tid=tid, type_="release_reservation", legs=legs,
                    reference_id=reference_id, key=key, metadata={"released": release},
                    bal=bal, reserved=reserved, now=now,
                )
                conn.commit()
        except self._pg_errors.UniqueViolation:
            with self._tenant_conn(tid) as conn:
                hit = self._fetch_idem(conn, key, tid)
                if hit:
                    return hit
            raise
        w = self.get_wallet(tid)
        e = LedgerEntry(
            transaction_id=tx_id, tenant_id=tid, type="release_reservation", legs=legs,
            balance_after=bal, reserved_after=reserved, reference_id=reference_id or "",
            idempotency_key=key, prev_hash=prev, entry_hash=h,
            metadata={"released": release}, created_at=now,
        )
        return CreditResult(ok=True, wallet=w, entry=e, transaction_id=tx_id)

    def capture_reservation(self, tenant_id, amount, *, type_="generation_cost",
                            reference_id="", idempotency_key="", metadata=None) -> CreditResult:
        err = validate_amount(amount)
        if err:
            return CreditResult(ok=False, reason=err)
        tid = str(tenant_id)
        key = idempotency_key or f"capture:{tid}:{uuid.uuid4().hex}"
        err = validate_idempotency_key(key)
        if err:
            return CreditResult(ok=False, reason=err)
        now = time.time()
        try:
            with self._tenant_conn(tid) as conn:
                hit = self._fetch_idem(conn, key, tid)
                if hit:
                    return hit
                row = conn.execute(
                    "SELECT * FROM credit_wallets WHERE tenant_id=%s FOR UPDATE", (tid,)
                ).fetchone()
                if not row:
                    return CreditResult(ok=False, reason="wallet_not_found")
                if int(row["reserved_balance"]) < int(amount):
                    return CreditResult(
                        ok=False, reason=f"insufficient_reserved:{row['reserved_balance']}",
                        wallet=self._row_wallet(row),
                    )
                if int(row["current_balance"]) < int(amount):
                    return CreditResult(
                        ok=False, reason=f"insufficient_balance:{row['current_balance']}",
                        wallet=self._row_wallet(row),
                    )
                upd = conn.execute(
                    """
                    UPDATE credit_wallets
                    SET current_balance = current_balance - %s,
                        reserved_balance = reserved_balance - %s,
                        updated_at = %s
                    WHERE tenant_id=%s AND reserved_balance >= %s AND current_balance >= %s
                    """,
                    (int(amount), int(amount), now, tid, int(amount), int(amount)),
                )
                if upd.rowcount == 0:
                    conn.rollback()
                    return CreditResult(ok=False, reason="capture_race", wallet=self.get_wallet(tid))
                bal = int(row["current_balance"]) - int(amount)
                reserved = int(row["reserved_balance"]) - int(amount)
                wa = user_wallet_account(tid)
                legs = [
                    LedgerLeg(SYSTEM_HOLDS, "debit", int(amount)),
                    LedgerLeg(f"hold:{tid}", "credit", int(amount)),
                    LedgerLeg(wa, "debit", int(amount)),
                    LedgerLeg(SYSTEM_REVENUE, "credit", int(amount)),
                ]
                meta = dict(metadata or {})
                meta["captured"] = int(amount)
                tx_id, prev, h = self._write_tx(
                    conn, tid=tid, type_=type_, legs=legs, reference_id=reference_id,
                    key=key, metadata=meta, bal=bal, reserved=reserved, now=now,
                )
                conn.commit()
        except self._pg_errors.UniqueViolation:
            with self._tenant_conn(tid) as conn:
                hit = self._fetch_idem(conn, key, tid)
                if hit:
                    return hit
            raise
        w = self.get_wallet(tid)
        e = LedgerEntry(
            transaction_id=tx_id, tenant_id=tid, type=type_, legs=legs,
            balance_after=bal, reserved_after=reserved, reference_id=reference_id or "",
            idempotency_key=key, prev_hash=prev, entry_hash=h,
            metadata=dict(metadata or {}, captured=int(amount)), created_at=now,
        )
        return CreditResult(ok=True, wallet=w, entry=e, transaction_id=tx_id)

    def expire_promotional(self, tenant_id: str) -> CreditResult:
        """Burn expired promotional balance (PG)."""
        import time as _time
        tid = str(tenant_id)
        w = self.ensure_wallet(tid)
        if int(w.promotional_balance) <= 0:
            return CreditResult(ok=True, reason="nothing_to_expire", wallet=w)
        exp = float(w.promo_expires_at or 0)
        if exp <= 0 or _time.time() < exp:
            return CreditResult(ok=True, reason="nothing_to_expire", wallet=w)
        amount = min(int(w.promotional_balance), int(w.current_balance))
        if amount <= 0:
            return CreditResult(ok=True, reason="nothing_to_expire", wallet=w)
        # Reuse deduct path with special type
        res = self.deduct(
            tid, amount, type_="promo_expired",
            reference_id=f"promo_expire:{tid}",
            idempotency_key=f"promo-expire-{tid}-{int(exp)}",
            metadata={"is_promotional": True, "expired_amount": amount},
        )
        if res.ok and res.wallet is not None:
            # zero promo fields
            try:
                with self._conn() as conn:
                    conn.execute(
                        "UPDATE credit_wallets SET promotional_balance=0, promo_expires_at=0, updated_at=%s WHERE tenant_id=%s",
                        (_time.time(), tid),
                    )
                    conn.commit()
                res.wallet.promotional_balance = 0
                res.wallet.promo_expires_at = 0.0
            except Exception:
                pass
        return res

    def reconcile(self, tenant_id: str) -> ReconcileReport:
        tid = str(tenant_id)
        wa = user_wallet_account(tid)
        with self._conn() as conn:
            wrow = conn.execute(
                "SELECT * FROM credit_wallets WHERE tenant_id=%s", (tid,)
            ).fetchone()
            # net wallet legs
            net_row = conn.execute(
                """
                SELECT COALESCE(SUM(
                    CASE WHEN side='credit' THEN amount ELSE -amount END
                ),0) AS net
                FROM credit_legs
                WHERE account_id=%s
                """,
                (wa,),
            ).fetchone()
            # unbalanced txs
            unbal = conn.execute(
                """
                SELECT COUNT(*) AS c FROM (
                  SELECT t.transaction_id
                  FROM credit_transactions t
                  JOIN credit_legs l ON l.transaction_id = t.transaction_id
                  GROUP BY t.transaction_id
                  HAVING SUM(CASE WHEN l.side='debit' THEN l.amount ELSE 0 END)
                       <> SUM(CASE WHEN l.side='credit' THEN l.amount ELSE 0 END)
                ) x
                """
            ).fetchone()
        w = self._row_wallet(wrow) if wrow else Wallet(tenant_id=tid)
        net = int((net_row or {}).get("net") or 0)
        unbalanced = int((unbal or {}).get("c") or 0)
        return ReconcileReport(
            ok=(net == w.current_balance and unbalanced == 0),
            tenant_id=tid,
            wallet_balance=w.current_balance,
            ledger_wallet_net=net,
            wallet_reserved=w.reserved_balance,
            unbalanced_transactions=unbalanced,
            drift_balance=w.current_balance - net,
        )

    def list_ledger(self, tenant_id: str, *, limit: int = 100) -> list[LedgerEntry]:
        tid = str(tenant_id)
        with self._conn() as conn:
            txs = conn.execute(
                """
                SELECT * FROM credit_transactions WHERE tenant_id=%s
                ORDER BY created_at DESC LIMIT %s
                """,
                (tid, int(limit)),
            ).fetchall()
            out = []
            for tx in txs:
                legs_rows = conn.execute(
                    "SELECT * FROM credit_legs WHERE transaction_id=%s",
                    (tx["transaction_id"],),
                ).fetchall()
                legs = [
                    LedgerLeg(str(r["account_id"]), str(r["side"]), int(r["amount"]))
                    for r in legs_rows
                ]
                meta = tx.get("metadata") or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                out.append(
                    LedgerEntry(
                        transaction_id=str(tx["transaction_id"]),
                        tenant_id=tid,
                        type=str(tx["type"]),
                        legs=legs,
                        balance_after=0,
                        reference_id=str(tx.get("reference_id") or ""),
                        idempotency_key=str(tx.get("idempotency_key") or ""),
                        prev_hash=str(tx.get("prev_hash") or ""),
                        entry_hash=str(tx.get("entry_hash") or ""),
                        metadata=dict(meta) if isinstance(meta, dict) else {},
                        created_at=float(tx.get("created_at") or 0),
                    )
                )
        return out

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
                str(r["resource_type"]), int(r["cost_per_unit"]),
                bool(r["is_active"]), int(r.get("version") or 1), str(r.get("description") or ""),
            )
            for r in rows
        ]
