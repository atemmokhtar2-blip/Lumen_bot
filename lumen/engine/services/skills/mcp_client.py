"""Minimal MCP client over HTTP JSON-RPC (Model Context Protocol).

Implements tools/list and tools/call against servers that speak MCP over
streamable HTTP or simple JSON-RPC POST (common for remote MCP gateways).

Env:
  MCP_SERVER_URL / MCP_SERVER_URLS
  MCP_HTTP_TIMEOUT=30
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _timeout() -> float:
    try:
        return max(5.0, min(120.0, float(os.getenv("MCP_HTTP_TIMEOUT") or "30")))
    except ValueError:
        return 30.0


class MCPClient:
    """JSON-RPC client for MCP-compatible HTTP endpoints."""

    def __init__(self, base_url: str) -> None:
        self.base_url = (base_url or "").rstrip("/")
        if not self.base_url:
            raise ValueError("mcp_base_url_required")

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        # Optional bearer for private MCP gateways
        token = (os.getenv("MCP_AUTH_TOKEN") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.post(
            self.base_url,
            data=json.dumps(payload),
            headers=headers,
            timeout=_timeout(),
        )
        resp.raise_for_status()
        # Some gateways return SSE; take last data line
        text = resp.text or ""
        if text.startswith("event:") or "data:" in text[:200]:
            data_lines = [
                ln[5:].strip()
                for ln in text.splitlines()
                if ln.startswith("data:")
            ]
            if not data_lines:
                return {"error": "empty_sse"}
            body = json.loads(data_lines[-1])
        else:
            body = resp.json()
        if isinstance(body, dict) and body.get("error"):
            err = body["error"]
            raise RuntimeError(err if isinstance(err, str) else json.dumps(err))
        if isinstance(body, dict) and "result" in body:
            return body["result"] if isinstance(body["result"], dict) else {"value": body["result"]}
        return body if isinstance(body, dict) else {"value": body}

    def list_tools(self) -> list[dict[str, Any]]:
        try:
            result = self._rpc("tools/list")
            tools = result.get("tools") if isinstance(result, dict) else None
            if isinstance(tools, list):
                return [t for t in tools if isinstance(t, dict)]
            return []
        except Exception:
            logger.exception("MCP tools/list failed url=%s", self.base_url)
            return []

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            result = self._rpc(
                "tools/call",
                {"name": name, "arguments": dict(arguments or {})},
            )
            if isinstance(result, dict) and "ok" in result:
                return result
            return {"ok": True, "result": result, "tool": name}
        except Exception as exc:
            logger.exception("MCP tools/call failed tool=%s", name)
            return {"ok": False, "error": f"{type(exc).__name__}:{exc}", "tool": name}


def mcp_list_tools(server_url: str | None = None) -> list[dict[str, Any]]:
    url = (server_url or os.getenv("MCP_SERVER_URL") or "").strip()
    if not url:
        return []
    return MCPClient(url).list_tools()


def mcp_call_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    server_url: str | None = None,
) -> dict[str, Any]:
    url = (server_url or os.getenv("MCP_SERVER_URL") or "").strip()
    if not url:
        return {"ok": False, "error": "MCP_SERVER_URL not set"}
    return MCPClient(url).call_tool(name, arguments)


__all__ = ["MCPClient", "mcp_list_tools", "mcp_call_tool"]
