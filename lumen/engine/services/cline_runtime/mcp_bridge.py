"""MCP bridge — real client via skills.mcp_client + registry sync.

Env:
  MCP_SERVER_URL / MCP_SERVER_URLS / ACTIVEPIECES_MCP_URL
  MCP_AUTH_TOKEN
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def mcp_enabled() -> bool:
    return bool(
        (
            os.getenv("MCP_SERVER_URLS")
            or os.getenv("MCP_SERVER_URL")
            or os.getenv("ACTIVEPIECES_MCP_URL")
            or ""
        ).strip()
    )


def list_integration_hints() -> list[str]:
    return [
        "payment_gateway",
        "llm_api",
        "webhook",
        "external_api",
        "gmail",
        "sheets",
        "crm_sync",
        "github",
        "browser",
    ]


def status() -> dict[str, Any]:
    out: dict[str, Any] = {
        "enabled": mcp_enabled(),
        "tools": [],
        "skills": [],
    }
    try:
        from lumen.engine.services.skills import list_skills, mcp_list_tools
        out["skills"] = list_skills()
        url = (os.getenv("MCP_SERVER_URL") or os.getenv("ACTIVEPIECES_MCP_URL") or "").strip()
        if url:
            out["tools"] = mcp_list_tools(url)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}:{exc}"
    return out


def call_activepieces_webhook(
    flow_id: str,
    payload: dict[str, Any],
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    import json
    import urllib.request

    base = (os.getenv("ACTIVEPIECES_WEBHOOK_BASE") or "").rstrip("/")
    if not base:
        return {"ok": False, "error": "ACTIVEPIECES_WEBHOOK_BASE not set"}
    url = f"{base}/{flow_id.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "status": resp.status, "body": body[:2000]}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


__all__ = [
    "call_activepieces_webhook",
    "list_integration_hints",
    "mcp_enabled",
    "status",
]
