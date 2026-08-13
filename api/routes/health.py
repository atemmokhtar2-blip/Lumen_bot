from __future__ import annotations

from aiohttp import web


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "ai-agent-7h-api", "version": "1.0.0"})


async def ready(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "ready": True})
