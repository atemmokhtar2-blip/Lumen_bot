"""TenantRepository adapter over existing platform stores."""
from __future__ import annotations

from lumen.domain.entities.tenant import Tenant


def _to_domain(raw: object) -> Tenant | None:
    if raw is None:
        return None
    return Tenant(
        tenant_id=str(getattr(raw, "tenant_id", "") or ""),
        name=str(getattr(raw, "name", "") or ""),
        plan_id=str(getattr(raw, "plan_id", "free") or "free"),
        brand_name=str(getattr(raw, "brand_name", "") or ""),
        brand_logo_url=str(getattr(raw, "brand_logo_url", "") or ""),
        primary_color=str(getattr(raw, "primary_color", "#2563eb") or "#2563eb"),
        support_email=str(getattr(raw, "support_email", "") or ""),
        custom_domain=str(getattr(raw, "custom_domain", "") or ""),
        api_key_hash=str(getattr(raw, "api_key_hash", "") or ""),
        api_key_prefix=str(getattr(raw, "api_key_prefix", "") or ""),
        owner_telegram_id=int(getattr(raw, "owner_telegram_id", 0) or 0),
        active=bool(getattr(raw, "active", True)),
        created_at=float(getattr(raw, "created_at", 0.0) or 0.0),
        metadata=dict(getattr(raw, "metadata", None) or {}),
    )


class PlatformTenantRepository:
    """Adapts lumen.platform.get_tenant_store() to the domain TenantRepository port."""

    def __init__(self, store: object | None = None) -> None:
        if store is None:
            from lumen.platform.tenants import get_tenant_store
            store = get_tenant_store()
        self._store = store

    def get(self, tenant_id: str) -> Tenant | None:
        return _to_domain(self._store.get(tenant_id))

    def authenticate(self, api_key: str) -> Tenant | None:
        return _to_domain(self._store.authenticate(api_key))

    def create(
        self,
        name: str,
        *,
        plan_id: str = "free",
        owner_telegram_id: int = 0,
        brand_name: str = "",
        brand_logo_url: str = "",
        primary_color: str = "#2563eb",
        support_email: str = "",
        custom_domain: str = "",
        **fields: object,
    ) -> tuple[Tenant, str]:
        result = self._store.create(
            name,
            plan_id=plan_id,
            owner_telegram_id=int(owner_telegram_id or 0),
            brand_name=brand_name or name,
            brand_logo_url=brand_logo_url,
            primary_color=primary_color or "#2563eb",
            support_email=support_email,
            custom_domain=custom_domain,
            **{k: v for k, v in fields.items() if v is not None},
        )
        if isinstance(result, tuple) and len(result) == 2:
            raw_t, key = result
            domain = _to_domain(raw_t)
            if domain is None:
                raise RuntimeError("tenant_create_failed")
            return domain, str(key)
        domain = _to_domain(result)
        if domain is None:
            raise RuntimeError("tenant_create_failed")
        return domain, ""

    def update_white_label(self, tenant_id: str, **fields: object) -> Tenant | None:
        updated = self._store.update_white_label(tenant_id, **fields)
        return _to_domain(updated)

    def rotate_key(self, tenant_id: str) -> str | None:
        return self._store.rotate_key(tenant_id)

    def list_all(self) -> list[Tenant]:
        rows = self._store.list_all() if hasattr(self._store, "list_all") else []
        out: list[Tenant] = []
        for r in rows or []:
            d = _to_domain(r)
            if d is not None:
                out.append(d)
        return out
