"""Official MCP Python SDK client (mcp package).

Falls back to HTTP JSON-RPC thin client only if SDK missing.
https://github.com/modelcontextprotocol/python-sdk
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def mcp_sdk_available() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except Exception:
        return False


async def list_tools_sdk(server_command: list[str] | None = None) -> list[dict[str, Any]]:
    """List tools via official MCP stdio client.

    Env MCP_SERVER_COMMAND e.g. 'npx,-y,@modelcontextprotocol/server-filesystem,/tmp'
    """
    if not mcp_sdk_available():
        return []
    raw = server_command or [
        p.strip() for p in (os.getenv("MCP_SERVER_COMMAND") or "").split(",") if p.strip()
    ]
    if not raw:
        return []
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=raw[0], args=raw[1:], env=None)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            tools = getattr(result, "tools", None) or []
            out = []
            for t in tools:
                out.append({
                    "name": getattr(t, "name", None) or str(t),
                    "description": getattr(t, "description", "") or "",
                    "inputSchema": getattr(t, "inputSchema", None) or {},
                })
            return out


def list_tools_sync() -> list[dict[str, Any]]:
    """Sync wrapper for registry bootstrap."""
    import asyncio
    try:
        return asyncio.run(list_tools_sdk())
    except Exception:
        logger.exception("official MCP list_tools failed")
        return []


__all__ = ["list_tools_sdk", "list_tools_sync", "mcp_sdk_available"]
