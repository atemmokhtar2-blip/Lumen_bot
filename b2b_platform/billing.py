"""Billing service — plan enforcement + Stripe-ready invoice hooks."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .metering import get_metering
from .plans import get_plan
from .tenants import get_tenant_store


@dataclass
class Invoice:
    invoice_id: str
    tenant_id: str
    plan_id: str
    amount_usd: float
    currency: str = "usd"
    status: str = "draft"  # draft | open | paid | void
    period: str = ""
    created_at: float = field(default_factory=time.time)
    paid_at: float = 0.0
    provider_ref: str = ""  # stripe invoice id later
    line_items: list[dict[str, Any]] = field(default_factory=list)


class BillingService:
    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root or os.getenv("OUTPUT_DIR", "/tmp/generated"))
        self.root = base / "platform" / "billing"
        self.root.mkdir(parents=True, exist_ok=True)

    def _inv_path(self, invoice_id: str) -> Path:
        return self.root / f"{invoice_id}.json"

    def enforce_generation(self, tenant_id: str) -> tuple[bool, str]:
        store = get_tenant_store()
        t = store.get(tenant_id)
        if not t or not t.active:
            return False, "tenant_inactive"
        plan = get_plan(t.plan_id)
        usage = get_metering().snapshot(tenant_id)
        limit = plan.generations_per_month
        if limit > 0 and int(usage.get("generations", 0)) >= limit:
            return False, f"generation_quota_exceeded:{limit}"
        return True, "ok"

    def enforce_hosting(self, tenant_id: str, current_hosted: int) -> tuple[bool, str]:
        store = get_tenant_store()
        t = store.get(tenant_id)
        if not t or not t.active:
            return False, "tenant_inactive"
        plan = get_plan(t.plan_id)
        if plan.hosted_bots > 0 and current_hosted >= plan.hosted_bots:
            return False, f"hosted_bots_quota_exceeded:{plan.hosted_bots}"
        if "managed_hosting" not in plan.features and plan.id == "free":
            return False, "plan_lacks_managed_hosting"
        return True, "ok"

    def enforce_api(self, tenant_id: str) -> tuple[bool, str]:
        store = get_tenant_store()
        t = store.get(tenant_id)
        if not t or not t.active:
            return False, "tenant_inactive"
        plan = get_plan(t.plan_id)
        if "api_access" not in plan.features and plan.id not in ("business", "enterprise", "pro"):
            # free gets limited API for onboarding
            pass
        if not get_metering().check_rpm(tenant_id, plan.api_rpm):
            return False, f"rate_limited:{plan.api_rpm}_rpm"
        return True, "ok"

    def create_monthly_invoice(self, tenant_id: str) -> Invoice | None:
        store = get_tenant_store()
        t = store.get(tenant_id)
        if not t:
            return None
        plan = get_plan(t.plan_id)
        period = time.strftime("%Y-%m", time.gmtime())
        inv = Invoice(
            invoice_id=f"inv_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            plan_id=plan.id,
            amount_usd=float(plan.price_usd_month),
            period=period,
            status="open" if plan.price_usd_month > 0 else "paid",
            line_items=[
                {
                    "description": f"{plan.name} plan — {period}",
                    "amount_usd": plan.price_usd_month,
                }
            ],
        )
        if plan.price_usd_month <= 0:
            inv.paid_at = time.time()
        self._inv_path(inv.invoice_id).write_text(
            json.dumps(asdict(inv), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return inv

    def mark_paid(self, invoice_id: str, provider_ref: str = "") -> Invoice | None:
        path = self._inv_path(invoice_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "paid"
        data["paid_at"] = time.time()
        if provider_ref:
            data["provider_ref"] = provider_ref
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return Invoice(**{k: v for k, v in data.items() if k in Invoice.__dataclass_fields__})

    def list_invoices(self, tenant_id: str) -> list[dict[str, Any]]:
        out = []
        for p in self.root.glob("inv_*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("tenant_id") == tenant_id:
                    out.append(data)
            except Exception:
                continue
        out.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return out

    def stripe_webhook_placeholder(self, event: dict[str, Any]) -> dict[str, Any]:
        """Ready for Stripe: checkout.session.completed / invoice.paid."""
        etype = (event or {}).get("type") or ""
        obj = (event or {}).get("data", {}).get("object") or {}
        if etype in ("invoice.paid", "checkout.session.completed"):
            inv_id = obj.get("metadata", {}).get("invoice_id") or obj.get("id") or ""
            if inv_id.startswith("inv_"):
                self.mark_paid(inv_id, provider_ref=str(obj.get("id") or ""))
            return {"ok": True, "handled": etype}
        return {"ok": True, "handled": False, "type": etype}


_BILL: BillingService | None = None


def get_billing() -> BillingService:
    global _BILL
    if _BILL is None:
        _BILL = BillingService()
    return _BILL
