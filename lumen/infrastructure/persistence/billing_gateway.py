"""BillingGateway adapter over platform billing + credits."""
from __future__ import annotations

from lumen.domain.entities.balance import Balance


class PlatformBillingGateway:
    """Maps lumen.platform.billing + credits → domain BillingGateway."""

    def get_balance(self, tenant_id: str) -> Balance:
        tid = (tenant_id or "").strip()
        try:
            from lumen.platform.credits import get_credit_service
            wallet = get_credit_service().get_wallet(tid)
            return Balance(
                tenant_id=tid,
                current=int(getattr(wallet, "current_balance", 0) or 0),
                reserved=int(getattr(wallet, "reserved_balance", 0) or 0),
                promotional=int(getattr(wallet, "promotional_balance", 0) or 0),
                currency=str(getattr(wallet, "currency", "credits") or "credits"),
                updated_at=float(getattr(wallet, "updated_at", 0.0) or 0.0),
                promo_expires_at=float(getattr(wallet, "promo_expires_at", 0.0) or 0.0),
            )
        except Exception:
            return Balance(tenant_id=tid)

    def enforce_api(self, tenant_id: str) -> tuple[bool, str]:
        from lumen.platform.billing import get_billing
        return get_billing().enforce_api(tenant_id)

    def enforce_generation(
        self, tenant_id: str, *, reserve: bool = True
    ) -> tuple[bool, str]:
        from lumen.platform.billing import get_billing
        return get_billing().enforce_generation(tenant_id, reserve=reserve)

    def enforce_hosting(
        self, tenant_id: str, current_hosted: int
    ) -> tuple[bool, str]:
        from lumen.platform.billing import get_billing
        return get_billing().enforce_hosting(tenant_id, current_hosted)

    def enforce_feature(self, tenant_id: str, feature: str) -> tuple[bool, str]:
        from lumen.platform.billing import get_billing
        return get_billing().enforce_feature(tenant_id, feature)
