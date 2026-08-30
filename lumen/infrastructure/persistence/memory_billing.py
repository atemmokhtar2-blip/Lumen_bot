"""In-memory billing gateway for unit tests."""
from __future__ import annotations

from lumen.domain.entities.balance import Balance


class InMemoryBillingGateway:
    def __init__(self) -> None:
        self._balances: dict[str, Balance] = {}
        self.api_blocked: set[str] = set()
        self.gen_blocked: set[str] = set()

    def seed(self, tenant_id: str, *, current: int = 0, reserved: int = 0) -> Balance:
        b = Balance(tenant_id=tenant_id, current=current, reserved=reserved)
        self._balances[tenant_id] = b
        return b

    def get_balance(self, tenant_id: str) -> Balance:
        return self._balances.get(tenant_id) or Balance(tenant_id=tenant_id)

    def enforce_api(self, tenant_id: str) -> tuple[bool, str]:
        if tenant_id in self.api_blocked:
            return False, "rate_limited:test"
        return True, "ok"

    def enforce_generation(
        self, tenant_id: str, *, reserve: bool = True
    ) -> tuple[bool, str]:
        if tenant_id in self.gen_blocked:
            return False, "generation_quota_exceeded:0"
        if reserve:
            b = self.get_balance(tenant_id)
            if b.available <= 0 and b.current > 0:
                return False, "insufficient_credits"
        return True, "ok"

    def enforce_hosting(
        self, tenant_id: str, current_hosted: int
    ) -> tuple[bool, str]:
        return True, "ok"

    def enforce_feature(self, tenant_id: str, feature: str) -> tuple[bool, str]:
        return True, "ok"
