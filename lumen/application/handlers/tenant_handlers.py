"""Tenant use-case handlers — depend only on domain ports."""
from __future__ import annotations

from lumen.application.commands.create_tenant import CreateTenantCommand
from lumen.application.queries.authenticate_tenant import AuthenticateTenantQuery
from lumen.application.queries.get_tenant import GetTenantQuery
from lumen.domain.entities.tenant import Tenant
from lumen.domain.repositories.tenant_repository import TenantRepository


def handle_create_tenant(
    cmd: CreateTenantCommand,
    *,
    tenants: TenantRepository,
) -> tuple[Tenant, str]:
    name = (cmd.name or "").strip()
    if not name:
        raise ValueError("name_required")
    plan_id = (cmd.plan_id or "free").strip().lower() or "free"
    return tenants.create(
        name,
        plan_id=plan_id,
        owner_telegram_id=int(cmd.owner_telegram_id or 0),
        brand_name=(cmd.brand_name or name).strip(),
        brand_logo_url=(cmd.brand_logo_url or "").strip(),
        primary_color=(cmd.primary_color or "#2563eb").strip(),
        support_email=(cmd.support_email or "").strip(),
        custom_domain=(cmd.custom_domain or "").strip(),
    )


def handle_authenticate_tenant(
    query: AuthenticateTenantQuery,
    *,
    tenants: TenantRepository,
) -> Tenant:
    key = (query.api_key or "").strip()
    if not key:
        raise PermissionError("missing_api_key")
    tenant = tenants.authenticate(key)
    if tenant is None:
        raise PermissionError("invalid_api_key")
    tenant.ensure_active()
    return tenant


def handle_get_tenant(
    query: GetTenantQuery,
    *,
    tenants: TenantRepository,
) -> Tenant:
    tid = (query.tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id_required")
    tenant = tenants.get(tid)
    if tenant is None:
        raise LookupError("tenant_not_found")
    return tenant
