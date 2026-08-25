from __future__ import annotations

from aiohttp import web

from lumen.identity import API_SERVICE_ID, API_VERSION


async def health(request: web.Request) -> web.Response:
    body: dict = {"ok": True, "service": API_SERVICE_ID, "version": API_VERSION}
    try:
        from lumen.engine.services.multi_agent import liveness
        body["multi_agent"] = liveness()
    except Exception as exc:
        body["multi_agent"] = {"ok": False, "error": type(exc).__name__}
    return web.json_response(body)


async def ready(request: web.Request) -> web.Response:
    body: dict = {"ok": True, "ready": True}
    try:
        from lumen.engine.services.multi_agent import readiness, health_snapshot
        ma = readiness()
        body["multi_agent"] = ma
        if not ma.get("ready", True):
            body["ready"] = False
            body["ok"] = False
            return web.json_response(body, status=503)
        body["multi_agent_health"] = health_snapshot(deep=False)
    except Exception as exc:
        body["multi_agent"] = {"ok": False, "error": type(exc).__name__}
        # multi-agent optional for core API readiness
    return web.json_response(body)
