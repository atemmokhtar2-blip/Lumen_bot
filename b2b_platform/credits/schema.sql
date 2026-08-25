-- Credits ledger schema (Phase 1). Applied by PostgresCreditsStore._ensure_schema.

CREATE TABLE IF NOT EXISTS credit_wallets (
    tenant_id TEXT PRIMARY KEY,
    current_balance BIGINT NOT NULL DEFAULT 0 CHECK (current_balance >= 0),
    reserved_balance BIGINT NOT NULL DEFAULT 0 CHECK (reserved_balance >= 0),
    currency TEXT NOT NULL DEFAULT 'credits',
    updated_at DOUBLE PRECISION NOT NULL DEFAULT 0,
    CONSTRAINT credit_wallets_reserved_le_current
        CHECK (reserved_balance <= current_balance)
);

CREATE TABLE IF NOT EXISTS credit_ledger (
    transaction_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    amount BIGINT NOT NULL,
    balance_after BIGINT NOT NULL,
    type TEXT NOT NULL,
    reference_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at DOUBLE PRECISION NOT NULL,
    CONSTRAINT credit_ledger_idempotency UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_credit_ledger_tenant_time
    ON credit_ledger (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_type
    ON credit_ledger (tenant_id, type);

CREATE TABLE IF NOT EXISTS credit_pricing_rules (
    resource_type TEXT PRIMARY KEY,
    cost_per_unit BIGINT NOT NULL CHECK (cost_per_unit >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL DEFAULT '',
    updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
);
