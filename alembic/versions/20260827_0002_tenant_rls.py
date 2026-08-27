"""Enable PostgreSQL Row-Level Security on tenant-scoped tables.

Uses session GUC app.tenant_id set by the application on each connection.
Even if application code has a bug, RLS blocks cross-tenant reads/writes.

Revision ID: 20260827_0002
Revises: 20260826_0001
"""
from __future__ import annotations

from alembic import op

revision = "20260827_0002"
down_revision = "20260826_0001"
branch_labels = None
depends_on = None

# Tables that store per-tenant data (must have tenant_id column)
_TENANT_TABLES = (
    "credit_wallets",
    "credit_transactions",
    "metering",
    "balance_lifecycle",
    "usage_ratings",
    "usage_batches",
)


def upgrade() -> None:
    # FORCE ROW LEVEL SECURITY so table owners cannot bypass
    for table in _TENANT_TABLES:
        op.execute(f'ALTER TABLE IF EXISTS "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE IF EXISTS "{table}" FORCE ROW LEVEL SECURITY')
        # Drop old policy if re-run
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON "{table}"
            FOR ALL
            USING (
                current_setting('app.rls_bypass', true) = 'on'
                OR (
                    COALESCE(NULLIF(current_setting('app.tenant_id', true), ''), '') <> ''
                    AND tenant_id = current_setting('app.tenant_id', true)
                )
            )
            WITH CHECK (
                current_setting('app.rls_bypass', true) = 'on'
                OR (
                    COALESCE(NULLIF(current_setting('app.tenant_id', true), ''), '') <> ''
                    AND tenant_id = current_setting('app.tenant_id', true)
                )
            )
            """
        )
    # tenants table: isolate by tenant_id primary key
    op.execute('ALTER TABLE IF EXISTS "tenants" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE IF EXISTS "tenants" FORCE ROW LEVEL SECURITY')
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "tenants"')
    op.execute(
        """
        CREATE POLICY tenant_isolation ON tenants
        FOR ALL
        USING (
            current_setting('app.rls_bypass', true) = 'on'
            OR (
                COALESCE(NULLIF(current_setting('app.tenant_id', true), ''), '') <> ''
                AND tenant_id = current_setting('app.tenant_id', true)
            )
        )
        WITH CHECK (
            current_setting('app.rls_bypass', true) = 'on'
            OR (
                COALESCE(NULLIF(current_setting('app.tenant_id', true), ''), '') <> ''
                AND tenant_id = current_setting('app.tenant_id', true)
            )
        )
        """
    )


def downgrade() -> None:
    for table in list(_TENANT_TABLES) + ["tenants"]:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE IF EXISTS "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE IF EXISTS "{table}" DISABLE ROW LEVEL SECURITY')
