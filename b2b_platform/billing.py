"""Billing service — plan enforcement + Stripe Checkout + invoices."""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .metering import get_metering
from .plans import get_plan
from .stripe_client import (
    create_billing_portal_session,
    create_checkout_session,
    retrieve_checkout_session,
    stripe_configured,
    verify_webhook_signature,
)
from .tenants import get_tenant_store
from .filelock import atomic_write_text, exclusive_lock

logger = logging.getLogger("b2b_platform.billing")


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
    provider_ref: str = ""
    checkout_session_id: str = ""
    line_items: list[dict[str, Any]] = field(default_factory=list)


class BillingService:
    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root or os.getenv("OUTPUT_DIR", "/tmp/generated"))
        self.root = base / "platform" / "billing"
        self.root.mkdir(parents=True, exist_ok=True)

    def _inv_path(self, invoice_id: str) -> Path:
        return self.root / f"{invoice_id}.json"

    def _save_invoice(self, inv: Invoice) -> None:
        path = self._inv_path(inv.invoice_id)
        with exclusive_lock(path):
            atomic_write_text(path, json.dumps(asdict(inv), ensure_ascii=False, indent=2))

    def _load_invoice(self, invoice_id: str) -> Invoice | None:
        path = self._inv_path(invoice_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Invoice(**{k: v for k, v in data.items() if k in Invoice.__dataclass_fields__})
        except Exception:
            return None

    def enforce_generation(self, tenant_id: str, *, reserve: bool = True) -> tuple[bool, str]:
        """Check generation quota. When reserve=True (default), atomically consume one unit.

        Atomic reserve closes the TOCTOU race where parallel requests all pass a
        stale read before any counter is incremented.
        """
        store = get_tenant_store()
        t = store.get(tenant_id)
        if not t or not t.active:
            return False, "tenant_inactive"
        plan = get_plan(t.plan_id)
        limit = plan.generations_per_month
        if reserve:
            ok, reason, _ = get_metering().try_reserve_generation(tenant_id, limit)
            return ok, reason
        usage = get_metering().snapshot(tenant_id)
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
        if not get_metering().check_rpm(tenant_id, plan.api_rpm):
            return False, f"rate_limited:{plan.api_rpm}_rpm"
        return True, "ok"

    def create_monthly_invoice(self, tenant_id: str, plan_id: str | None = None) -> Invoice | None:
        store = get_tenant_store()
        t = store.get(tenant_id)
        if not t:
            return None
        plan = get_plan(plan_id or t.plan_id)
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
        self._save_invoice(inv)
        return inv

    def mark_paid(self, invoice_id: str, provider_ref: str = "") -> Invoice | None:
        inv = self._load_invoice(invoice_id)
        if not inv:
            return None
        inv.status = "paid"
        inv.paid_at = time.time()
        if provider_ref:
            inv.provider_ref = provider_ref
        self._save_invoice(inv)
        return inv

    def apply_plan(self, tenant_id: str, plan_id: str, *, stripe_customer: str = "") -> bool:
        """Atomically set plan_id / active / metadata under one exclusive lock.

        Previously: get() → mutate local copy → update_white_label() (reloads
        and may drop metadata) → overwrite _by_id + _save(). That race could
        lose stripe_customer_id / last_plan_change under concurrent writes.
        """
        store = get_tenant_store()

        def _do():
            cur = store._by_id.get(tenant_id)
            if not cur:
                return False
            meta = dict(cur.metadata or {})
            if stripe_customer:
                meta["stripe_customer_id"] = stripe_customer
            meta["last_plan_change"] = time.time()
            cur.metadata = meta
            cur.plan_id = (plan_id or cur.plan_id).lower()
            cur.active = True
            return True

        ok = bool(store._mutate(_do))
        if ok:
            logger.info("tenant %s upgraded to plan %s", tenant_id, (plan_id or "").lower())
        return ok

    def start_checkout(
        self,
        tenant_id: str,
        plan_id: str,
        *,
        success_url: str = "",
        cancel_url: str = "",
        customer_email: str = "",
    ) -> dict[str, Any]:
        store = get_tenant_store()
        t = store.get(tenant_id)
        if not t:
            return {"ok": False, "error": "tenant_not_found"}
        plan = get_plan(plan_id)
        if plan.id == "free":
            self.apply_plan(tenant_id, "free")
            return {"ok": True, "plan_id": "free", "checkout_required": False}
        if plan.id == "enterprise":
            return {
                "ok": False,
                "error": "enterprise_sales_required",
                "hint": "Contact sales for enterprise pricing",
            }

        base = (os.getenv("PUBLIC_BASE_URL") or "http://localhost:8080").rstrip("/")
        success_url = success_url or f"{base}/v1/billing/checkout/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = cancel_url or f"{base}/v1/billing/checkout/cancel"

        inv = self.create_monthly_invoice(tenant_id, plan_id=plan.id)
        if not inv:
            return {"ok": False, "error": "invoice_failed"}

        if not stripe_configured():
            # Dev fallback: mark open invoice, return mock URL
            return {
                "ok": True,
                "checkout_required": True,
                "stripe_configured": False,
                "invoice_id": inv.invoice_id,
                "url": None,
                "message": "STRIPE_SECRET_KEY not set — invoice created as open",
                "dev_activate": f"POST /v1/billing/dev/activate with invoice_id (admin only)",
            }

        session = create_checkout_session(
            tenant_id=tenant_id,
            plan_id=plan.id,
            customer_email=customer_email or t.support_email or "",
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=inv.invoice_id,
            metadata={"invoice_id": inv.invoice_id},
        )
        if not session.get("ok"):
            return session
        inv.checkout_session_id = str(session.get("session_id") or "")
        inv.provider_ref = inv.checkout_session_id
        self._save_invoice(inv)
        return {
            "ok": True,
            "checkout_required": True,
            "stripe_configured": True,
            "invoice_id": inv.invoice_id,
            "session_id": session.get("session_id"),
            "url": session.get("url"),
        }

    def portal(self, tenant_id: str, return_url: str = "") -> dict[str, Any]:
        store = get_tenant_store()
        t = store.get(tenant_id)
        if not t:
            return {"ok": False, "error": "tenant_not_found"}
        customer = (t.metadata or {}).get("stripe_customer_id") or ""
        base = (os.getenv("PUBLIC_BASE_URL") or "http://localhost:8080").rstrip("/")
        return_url = return_url or f"{base}/v1/dashboard"
        return create_billing_portal_session(customer_id=customer, return_url=return_url)

    def handle_stripe_event(self, event: dict[str, Any]) -> dict[str, Any]:
        etype = (event or {}).get("type") or ""
        obj = (event or {}).get("data", {}).get("object") or {}
        meta = obj.get("metadata") or {}
        tenant_id = meta.get("tenant_id") or obj.get("client_reference_id") or ""
        plan_id = meta.get("plan_id") or ""
        invoice_id = meta.get("invoice_id") or ""

        if etype == "checkout.session.completed":
            if not tenant_id:
                tenant_id = obj.get("client_reference_id") or ""
            if not plan_id:
                plan_id = (obj.get("metadata") or {}).get("plan_id") or ""
            customer = obj.get("customer") or ""
            if tenant_id and plan_id:
                self.apply_plan(tenant_id, plan_id, stripe_customer=str(customer))
            if invoice_id:
                self.mark_paid(invoice_id, provider_ref=str(obj.get("id") or ""))
            elif tenant_id:
                # best-effort: pay latest open invoice for tenant
                for inv in self.list_invoices(tenant_id):
                    if inv.get("status") == "open":
                        self.mark_paid(inv["invoice_id"], provider_ref=str(obj.get("id") or ""))
                        break
            return {"ok": True, "handled": etype, "tenant_id": tenant_id, "plan_id": plan_id}

        if etype in ("invoice.paid", "invoice.payment_succeeded"):
            if invoice_id:
                self.mark_paid(invoice_id, provider_ref=str(obj.get("id") or ""))
            if tenant_id and plan_id:
                self.apply_plan(tenant_id, plan_id, stripe_customer=str(obj.get("customer") or ""))
            return {"ok": True, "handled": etype}

        if etype in ("customer.subscription.updated", "customer.subscription.created"):
            if tenant_id and plan_id:
                self.apply_plan(tenant_id, plan_id, stripe_customer=str(obj.get("customer") or ""))
            return {"ok": True, "handled": etype, "tenant_id": tenant_id}

        if etype == "customer.subscription.deleted":
            if tenant_id:
                self.apply_plan(tenant_id, "free")
            return {"ok": True, "handled": etype, "tenant_id": tenant_id, "plan_id": "free"}

        return {"ok": True, "handled": False, "type": etype}

    def complete_checkout_session(self, session_id: str) -> dict[str, Any]:
        """Fallback when webhook is delayed — poll session and apply plan."""
        data = retrieve_checkout_session(session_id)
        if not data:
            return {"ok": False, "error": "session_not_found"}
        if data.get("payment_status") not in ("paid", "no_payment_required") and data.get("status") != "complete":
            return {"ok": False, "error": "not_paid", "status": data.get("status"), "payment_status": data.get("payment_status")}
        event = {"type": "checkout.session.completed", "data": {"object": data}}
        return self.handle_stripe_event(event)

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


_BILL: BillingService | None = None


def get_billing() -> BillingService:
    global _BILL
    if _BILL is None:
        _BILL = BillingService()
    return _BILL
