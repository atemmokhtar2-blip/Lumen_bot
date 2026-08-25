-- Credits ledger Phase 1 (hardened)
-- Balance moves: amount != 0. Reservation holds: reservation_delta != 0.
-- Never UPDATE/DELETE ledger rows from application code.

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
    amount BIGINT NOT NULL DEFAULT 0,
    reservation_delta BIGINT NOT NULL DEFAULT 0,
    balance_after BIGINT NOT NULL,
    reserved_after BIGINT NOT NULL DEFAULT 0,
    type TEXT NOT NULL,
    counterparty TEXT NOT NULL DEFAULT 'system',
    reference_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at DOUBLE PRECISION NOT NULL,
    CONSTRAINT credit_ledger_idempotency UNIQUE (idempotency_key),
    CONSTRAINT credit_ledger_nonzero_effect
        CHECK (amount <> 0 OR reservation_delta <> 0)
);

CREATE INDEX IF NOT EXISTS idx_credit_ledger_tenant_time
    ON credit_ledger (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_type
    ON credit_ledger (tenant_id, type);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_reference
    ON credit_ledger (tenant_id, reference_id);

CREATE TABLE IF NOT EXISTS credit_pricing_rules (
    resource_type TEXT PRIMARY KEY,
    cost_per_unit BIGINT NOT NULL CHECK (cost_per_unit >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL DEFAULT '',
    updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
);
