"""Admin secret-rotation status and recording (Phase B)."""
from __future__ import annotations

import logging

from aiohttp import web

from lumen.api.auth import require_admin
from lumen.api.security import parse_json_object_bytes, read_capped_body

logger = logging.getLogger("lumen.api.secret_rotation")


async def rotation_status(request: web.Request) -> web.Response:
    require_admin(request)
    from lumen.platform.secret_rotation import rotation_status as _status

    return web.json_response({"ok": True, "secrets": _status()})


async def rotation_record(request: web.Request) -> web.Response:
    """POST {\"name\": \"PLATFORM_ADMIN_TOKEN\"} after rotating in Secret Manager."""
    require_admin(request)
    raw = await read_capped_body(request, max_bytes=4096)
    body = parse_json_object_bytes(raw)
    name = str(body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "name_required"}, status=400)
    from lumen.platform.secret_rotation import record_rotation

    ok = record_rotation(name)
    return web.json_response({"ok": ok, "name": name}, status=200 if ok else 503)
