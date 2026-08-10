"""Stripe HTTP client — Checkout + webhook verification (no hard SDK dependency).

Uses the official Stripe REST API via `requests`. When STRIPE_SECRET_KEY is
unset, methods return structured errors so local/dev still works.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger("b2b_platform.stripe")

STRIPE_API = "https://api.stripe.com/v1"


def stripe_configured() -> bool:
    return bool((os.getenv("STRIPE_SECRET_KEY") or "").strip())


def _secret() -> str:
    return (os.getenv("STRIPE_SECRET_KEY") or "").strip()


def _price_for_plan(plan_id: str) -> str:
    """Map plan → Stripe Price ID from env."""
    key = f"STRIPE_PRICE_{plan_id.upper()}"
    return (os.getenv(key) or "").strip()


def create_checkout_session(
    *,
    tenant_id: str,
    plan_id: str,
    customer_email: str = "",
    success_url: str,
    cancel_url: str,
    client_reference_id: str = "",
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not stripe_configured():
        return {"ok": False, "error": "stripe_not_configured"}
    price = _price_for_plan(plan_id)
    if not price:
        return {
            "ok": False,
            "error": f"missing_price_id",
            "hint": f"Set STRIPE_PRICE_{plan_id.upper()} to a Stripe Price ID",
        }
    meta = {
        "tenant_id": tenant_id,
        "plan_id": plan_id,
        **(metadata or {}),
    }
    data: dict[str, Any] = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][price]": price,
        "line_items[0][quantity]": 1,
        "client_reference_id": client_reference_id or tenant_id,
        "metadata[tenant_id]": tenant_id,
        "metadata[plan_id]": plan_id,
        "subscription_data[metadata][tenant_id]": tenant_id,
        "subscription_data[metadata][plan_id]": plan_id,
        "allow_promotion_codes": "true",
    }
    if customer_email:
        data["customer_email"] = customer_email
    for k, v in meta.items():
        data[f"metadata[{k}]"] = str(v)

    try:
        r = requests.post(
            f"{STRIPE_API}/checkout/sessions",
            data=data,
            auth=(_secret(), ""),
            timeout=30,
        )
        body = r.json() if r.content else {}
        if r.status_code >= 400:
            return {
                "ok": False,
                "error": "stripe_api_error",
                "status": r.status_code,
                "detail": body.get("error", {}).get("message") or body,
            }
        return {
            "ok": True,
            "session_id": body.get("id"),
            "url": body.get("url"),
            "customer": body.get("customer"),
            "raw": {"id": body.get("id"), "status": body.get("status")},
        }
    except Exception as exc:
        logger.exception("checkout session failed")
        return {"ok": False, "error": "stripe_request_failed", "detail": str(exc)[:300]}


def create_billing_portal_session(
    *,
    customer_id: str,
    return_url: str,
) -> dict[str, Any]:
    if not stripe_configured():
        return {"ok": False, "error": "stripe_not_configured"}
    if not customer_id:
        return {"ok": False, "error": "customer_id_required"}
    try:
        r = requests.post(
            f"{STRIPE_API}/billing_portal/sessions",
            data={"customer": customer_id, "return_url": return_url},
            auth=(_secret(), ""),
            timeout=30,
        )
        body = r.json() if r.content else {}
        if r.status_code >= 400:
            return {
                "ok": False,
                "error": "stripe_api_error",
                "detail": body.get("error", {}).get("message") or body,
            }
        return {"ok": True, "url": body.get("url")}
    except Exception as exc:
        return {"ok": False, "error": "stripe_request_failed", "detail": str(exc)[:300]}


def verify_webhook_signature(
    payload: bytes,
    sig_header: str,
    tolerance: int = 300,
) -> bool:
    """Verify Stripe-Signature header (t=...,v1=...)."""
    secret = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        # Production (Stripe live key present) must never skip verification —
        # otherwise anyone can POST forged checkout.session.completed events
        # and upgrade tenants for free.
        if stripe_configured():
            logger.error("STRIPE_WEBHOOK_SECRET required when STRIPE_SECRET_KEY is set")
            return False
        # Dev-only fallback when Stripe is not configured at all
        logger.warning("STRIPE_WEBHOOK_SECRET unset (dev only) — skipping signature verify")
        return True
    if not sig_header:
        return False
    parts = {}
    for item in sig_header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts.setdefault(k.strip(), []).append(v.strip())
    try:
        timestamp = int((parts.get("t") or ["0"])[0])
    except ValueError:
        return False
    if abs(int(time.time()) - timestamp) > tolerance:
        return False
    signed = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    candidates = parts.get("v1") or []
    return any(hmac.compare_digest(expected, c) for c in candidates)


def retrieve_checkout_session(session_id: str) -> dict[str, Any]:
    if not stripe_configured() or not session_id:
        return {}
    try:
        r = requests.get(
            f"{STRIPE_API}/checkout/sessions/{session_id}",
            auth=(_secret(), ""),
            timeout=30,
        )
        return r.json() if r.ok else {}
    except Exception:
        return {}
