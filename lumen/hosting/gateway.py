"""API Gateway helpers — Traefik / Caddy / Nginx snippets for hosted bots.

Production path uses Traefik file-provider (ingress.write_traefik_route).
This module exposes a single entry for operators and architecture docs generation.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("tbe.hosting.gateway")


def write_routes_for_instance(instance_id: str, *, enabled: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from lumen.engine.services.hosting.ingress import write_traefik_route, write_caddy_route

        out["traefik"] = write_traefik_route(instance_id=instance_id, enabled=enabled)
        out["caddy"] = write_caddy_route(instance_id=instance_id, enabled=enabled)
    except Exception as exc:
        out["error"] = type(exc).__name__
        logger.warning("gateway routes failed: %s", type(exc).__name__)
    return out


def nginx_snippet(instance_id: str, upstream: str = "127.0.0.1:8080") -> str:
    """Optional Nginx location for path-based routing to the API webhook endpoint."""
    return f"""
# Lumen host bot {instance_id}
location /v1/hooks/telegram/{instance_id} {{
    proxy_pass http://{upstream};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Telegram-Bot-Api-Secret-Token $http_x_telegram_bot_api_secret_token;
}}
""".strip()


def gateway_mode() -> str:
    return (os.environ.get("TBE_HOST_GATEWAY") or "traefik").strip().lower()


__all__ = ["write_routes_for_instance", "nginx_snippet", "gateway_mode"]
