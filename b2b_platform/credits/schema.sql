-- World-class credits: double-entry legs + immutable ledger + wallet projection.
-- Application MUST NOT UPDATE/DELETE credit_transactions or credit_legs.

CREATE TABLE IF NOT EXISTS credit_accounts (
    account_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,  -- user_wallet | system_treasury | system_revenue | system_holds
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
CREATE INDEX IF NOT EXISTS idx_credit_tx_reference ON credit_transactions (tenant_id, reference_id);

CREATE TABLE IF NOT EXISTS credit_pricing_rules (
    resource_type TEXT PRIMARY KEY,
    cost_per_unit BIGINT NOT NULL CHECK (cost_per_unit >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL DEFAULT '',
    updated_at DOUBLE PRECISION NOT NULL DEFAULT 0
);

-- Immutability: block UPDATE/DELETE on ledger tables
CREATE OR REPLACE FUNCTION credit_ledger_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'credit_ledger_immutable: % on % not allowed', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_credit_tx_no_update ON credit_transactions;
CREATE TRIGGER trg_credit_tx_no_update
  BEFORE UPDATE OR DELETE ON credit_transactions
  FOR EACH ROW EXECUTE PROCEDURE credit_ledger_immutable();

DROP TRIGGER IF EXISTS trg_credit_legs_no_update ON credit_legs;
CREATE TRIGGER trg_credit_legs_no_update
  BEFORE UPDATE OR DELETE ON credit_legs
  FOR EACH ROW EXECUTE PROCEDURE credit_ledger_immutable();
