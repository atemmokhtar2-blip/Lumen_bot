"""Dashboard aggregate for white-label / B2B consoles."""
from __future__ import annotations

from aiohttp import web

from lumen.api.auth import require_tenant
from lumen.platform.billing import get_billing
from lumen.platform.metering import get_metering
from lumen.platform.plans import get_plan
from lumen.engine.services.hosting import get_hosting_service


async def overview(request: web.Request) -> web.Response:
    tenant = require_tenant(request)
    plan = get_plan(tenant.plan_id)
    usage = get_metering().snapshot(tenant.tenant_id)
    uid = abs(hash(tenant.tenant_id)) % (10**9)
    hosts = get_hosting_service().list_for_user(uid)
    invoices = get_billing().list_invoices(tenant.tenant_id)[:5]
    return web.json_response(
        {
            "ok": True,
            "tenant": tenant.public_dict(),
            "plan": plan.__dict__,
            "usage": usage,
            "hosting": {
                "count": len(hosts),
                "running": sum(1 for h in hosts if h.status == "running"),
                "instances": [
                    {
                        "instance_id": h.instance_id,
                        "status": h.status,
                        "bot_username": h.bot_username,
                    }
                    for h in hosts[:20]
                ],
            },
            "invoices_preview": invoices,
            "product_surfaces": {
                "b2b_api": True,
                "white_label": plan.white_label,
                "managed_hosting": "managed_hosting" in plan.features or plan.id != "free",
                "consumer_telegram_bot": True,
            },
        }
    )
