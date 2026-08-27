"""Tighten RLS: fail-closed when app.tenant_id is unset.

Previous policy allowed all rows when app.tenant_id was NULL/empty — a bypass hole.
New policy requires a non-empty app.tenant_id matching tenant_id, unless
app.rls_bypass=on (schema migrations / platform maintenance only).

Revision ID: 20260827_0003
Revises: 20260827_0002
"""
from __future__ import annotations

from alembic import op

revision = "20260827_0003"
down_revision = "20260827_0002"
branch_labels = None
depends_on = None

_TENANT_TABLES = (
    "credit_wallets",
    "credit_transactions",
    "metering",
    "balance_lifecycle",
    "usage_ratings",
    "usage_batches",
    "tenants",
)

# Fail-closed: no tenant GUC ⇒ no rows. Bypass only via explicit app.rls_bypass=on.
_POLICY_USING = """
(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        COALESCE(NULLIF(current_setting('app.tenant_id', true), ''), '') <> ''
        AND tenant_id = current_setting('app.tenant_id', true)
    )
)
"""

_POLICY_CHECK = """
(
    current_setting('app.rls_bypass', true) = 'on'
    OR (
        COALESCE(NULLIF(current_setting('app.tenant_id', true), ''), '') <> ''
        AND tenant_id = current_setting('app.tenant_id', true)
    )
)
"""


def upgrade() -> None:
    for table in _TENANT_TABLES:
        op.execute(f'ALTER TABLE IF EXISTS "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE IF EXISTS "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON "{table}"
            FOR ALL
            USING {_POLICY_USING}
            WITH CHECK {_POLICY_CHECK}
            """
        )


def downgrade() -> None:
    # Restore previous (weaker) policy for rollback only
    weak = """
(
    tenant_id = current_setting('app.tenant_id', true)
    OR current_setting('app.tenant_id', true) IS NULL
    OR current_setting('app.tenant_id', true) = ''
)
"""
    for table in _TENANT_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON "{table}"
            FOR ALL
            USING {weak}
            WITH CHECK {weak}
            """
        )
