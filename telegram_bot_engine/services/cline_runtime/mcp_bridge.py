"""MCP bridge stub for Activepieces / external integrations.

Phase 3: define the contract. Live MCP client is optional when
ACTIVEPIECES_MCP_URL is set; otherwise tools report not_configured.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def mcp_enabled() -> bool:
    return bool((os.getenv("ACTIVEPIECES_MCP_URL") or os.getenv("MCP_SERVER_URL") or "").strip())


def list_integration_hints() -> list[str]:
    """Known integration labels Core may put on IR.capabilities_gap."""
    return [
        "payment_gateway",
        "llm_api",
        "webhook",
        "external_api",
        "gmail",
        "sheets",
        "crm_sync",
    ]


def call_activepieces_webhook(
    flow_id: str,
    payload: dict[str, Any],
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """POST to Activepieces webhook URL pattern if configured.

    Env:
      ACTIVEPIECES_WEBHOOK_BASE=https://.../api/v1/webhooks/
    """
    base = (os.getenv("ACTIVEPIECES_WEBHOOK_BASE") or "").rstrip("/")
    if not base:
        return {"ok": False, "error": "ACTIVEPIECES_WEBHOOK_BASE not set"}
    url = f"{base}/{flow_id.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    token = (os.getenv("ACTIVEPIECES_TOKEN") or "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"raw": raw[:2000]}
            return {"ok": True, "status": getattr(resp, "status", 200), "data": body}
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "error": f"http_{exc.code}",
            "body": exc.read()[:500].decode("utf-8", errors="replace"),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def status() -> dict[str, Any]:
    return {
        "mcp_enabled": mcp_enabled(),
        "activepieces_webhook": bool((os.getenv("ACTIVEPIECES_WEBHOOK_BASE") or "").strip()),
        "hints": list_integration_hints(),
    }


__all__ = [
    "call_activepieces_webhook",
    "list_integration_hints",
    "mcp_enabled",
    "status",
]
