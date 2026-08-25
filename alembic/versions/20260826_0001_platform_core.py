"""platform core tables: tenants, metering, credits, lifecycle, usage, ratings

Revision ID: 20260826_0001
Revises:
Create Date: 2026-08-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260826_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
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

    CREATE TABLE IF NOT EXISTS balance_lifecycle (
        tenant_id TEXT PRIMARY KEY,
        state TEXT NOT NULL DEFAULT 'active',
        last_topup_at DOUBLE PRECISION NOT NULL DEFAULT 0,
        last_spend_at DOUBLE PRECISION NOT NULL DEFAULT 0,
        grace_until DOUBLE PRECISION NOT NULL DEFAULT 0,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS usage_ratings (
        id BIGSERIAL PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        resource_type TEXT NOT NULL,
        units DOUBLE PRECISION NOT NULL DEFAULT 0,
        unit_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
        total_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
        currency TEXT NOT NULL DEFAULT 'credits',
        reference_id TEXT NOT NULL DEFAULT '',
        created_at DOUBLE PRECISION NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_usage_ratings_tenant ON usage_ratings(tenant_id, created_at DESC);

    CREATE TABLE IF NOT EXISTS usage_batches (
        batch_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        period TEXT NOT NULL DEFAULT '',
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at DOUBLE PRECISION NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_usage_batches_tenant ON usage_batches(tenant_id);

    CREATE TABLE IF NOT EXISTS credit_accounts (
        account_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT '',
        currency TEXT NOT NULL DEFAULT 'credits',
        created_at DOUBLE PRECISION NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS credit_wallets (
        tenant_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL UNIQUE REFERENCES credit_accounts(account_id),
        current_balance BIGINT NOT NULL DEFAULT 0 CHECK (current_balance >= 0),
        reserved_balance BIGINT NOT NULL DEFAULT 0 CHECK (reserved_balance >= 0),
        currency TEXT NOT NULL DEFAULT 'credits',
        promotional_balance BIGINT NOT NULL DEFAULT 0 CHECK (promotional_balance >= 0),
        promo_expires_at DOUBLE PRECISION NOT NULL DEFAULT 0,
        updated_at DOUBLE PRECISION NOT NULL DEFAULT 0,
        CONSTRAINT credit_wallets_reserved_le_current CHECK (reserved_balance <= current_balance)
    );

    CREATE TABLE IF NOT EXISTS credit_transactions (
        transaction_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        type TEXT NOT NULL,
        reference_id TEXT NOT NULL DEFAULT '',
        idempotency_key TEXT NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        prev_hash TEXT NOT NULL DEFAULT '',
        entry_hash TEXT NOT NULL DEFAULT '',
        created_at DOUBLE PRECISION NOT NULL,
        CONSTRAINT credit_tx_idempotency UNIQUE (idempotency_key)
    );

    CREATE TABLE IF NOT EXISTS credit_legs (
        leg_id BIGSERIAL PRIMARY KEY,
        transaction_id TEXT NOT NULL REFERENCES credit_transactions(transaction_id),
        account_id TEXT NOT NULL REFERENCES credit_accounts(account_id),
        side TEXT NOT NULL CHECK (side IN ('debit', 'credit')),
        amount BIGINT NOT NULL CHECK (amount > 0),
        created_at DOUBLE PRECISION NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_credit_legs_tx ON credit_legs (transaction_id);
    CREATE INDEX IF NOT EXISTS idx_credit_legs_account ON credit_legs (account_id);
    CREATE INDEX IF NOT EXISTS idx_credit_tx_tenant_time ON credit_transactions (tenant_id, created_at DESC);
    """)


def downgrade() -> None:
    # Destructive — only for disposable environments
    op.execute("""
    DROP TABLE IF EXISTS credit_legs CASCADE;
    DROP TABLE IF EXISTS credit_transactions CASCADE;
    DROP TABLE IF EXISTS credit_wallets CASCADE;
    DROP TABLE IF EXISTS credit_accounts CASCADE;
    DROP TABLE IF EXISTS usage_batches CASCADE;
    DROP TABLE IF EXISTS usage_ratings CASCADE;
    DROP TABLE IF EXISTS balance_lifecycle CASCADE;
    DROP TABLE IF EXISTS metering CASCADE;
    DROP TABLE IF EXISTS tenants CASCADE;
    """)
