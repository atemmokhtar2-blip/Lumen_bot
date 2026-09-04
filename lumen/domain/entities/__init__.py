"""Domain entities — lazy exports to avoid import-order coupling."""
from __future__ import annotations

from typing import Any

__all__ = ["Tenant", "Job", "Invoice", "Balance", "Referral", "ReferralStats"]


def __getattr__(name: str) -> Any:
    if name == "Tenant":
        from lumen.domain.entities.tenant import Tenant
        return Tenant
    if name == "Job":
        from lumen.domain.entities.job import Job
        return Job
    if name == "Invoice":
        from lumen.domain.entities.invoice import Invoice
        return Invoice
    if name == "Balance":
        from lumen.domain.entities.balance import Balance
        return Balance
    if name == "Referral":
        from lumen.domain.entities.referral import Referral
        return Referral
    if name == "ReferralStats":
        from lumen.domain.entities.referral import ReferralStats
        return ReferralStats
    raise AttributeError(name)
