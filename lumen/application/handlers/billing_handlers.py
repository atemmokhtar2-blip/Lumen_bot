"""Billing / balance use-case handlers — domain ports only."""
from __future__ import annotations

from lumen.application.queries.enforce_api import EnforceApiQuery
from lumen.application.queries.enforce_generation import EnforceGenerationQuery
from lumen.application.queries.get_balance import GetBalanceQuery
from lumen.domain.entities.balance import Balance
from lumen.domain.repositories.billing_gateway import BillingGateway


def handle_get_balance(
    query: GetBalanceQuery,
    *,
    billing: BillingGateway,
) -> Balance:
    tid = (query.tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id_required")
    return billing.get_balance(tid)


def handle_enforce_api(
    query: EnforceApiQuery,
    *,
    billing: BillingGateway,
) -> None:
    """Raise PermissionError with stable reason if API access denied."""
    tid = (query.tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id_required")
    ok, reason = billing.enforce_api(tid)
    if not ok:
        raise PermissionError(reason or "api_forbidden")


def handle_enforce_generation(
    query: EnforceGenerationQuery,
    *,
    billing: BillingGateway,
) -> None:
    tid = (query.tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id_required")
    ok, reason = billing.enforce_generation(tid, reserve=bool(query.reserve))
    if not ok:
        raise PermissionError(reason or "generation_forbidden")
