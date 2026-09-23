"""Product API Gateway integration for permanent hosted bots.

Orchestrates Traefik + Caddy dynamic configs so each bot has a stable
webhook router. Used by HostingService.start/stop — not a standalone script.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("tbe.hosting.gateway")


def write_routes_for_instance(instance_id: str, *, enabled: bool = True) -> dict[str, Any]:
    """Materialize gateway routes for one bot instance (Traefik + Caddy)."""
    out: dict[str, Any] = {"instance_id": instance_id, "enabled": enabled}
    try:
        from lumen.engine.services.hosting.ingress import (
            write_traefik_route,
            write_caddy_route,
            public_url_for_instance,
            webhook_path,
            api_backend_url,
        )

        out["public_base_url"] = public_url_for_instance(instance_id)
        out["webhook_path"] = webhook_path(instance_id)
        out["backend"] = api_backend_url()
        out["traefik"] = write_traefik_route(instance_id=instance_id, enabled=enabled)
        out["caddy"] = write_caddy_route(instance_id=instance_id, enabled=enabled)
        out["ok"] = bool(
            (out["traefik"] or {}).get("written")
            or (out["caddy"] or {}).get("written")
            or not (
                os.environ.get("TBE_TRAEFIK_DYNAMIC_DIR")
                or os.environ.get("TBE_CADDY_DYNAMIC_DIR")
            )
        )
    except Exception as exc:
        out["ok"] = False
        out["error"] = type(exc).__name__
        logger.exception("gateway write_routes failed instance=%s", instance_id)
    return out


def remove_routes_for_instance(instance_id: str) -> dict[str, Any]:
    return write_routes_for_instance(instance_id, enabled=False)


def nginx_snippet(instance_id: str, upstream: str = "") -> str:
    from lumen.engine.services.hosting.ingress import api_backend_url, webhook_path

    up = (upstream or api_backend_url()).replace("http://", "").replace("https://", "")
    wh = webhook_path(instance_id)
    return "\n".join(
        [
            f"# Lumen permanent host webhook — {instance_id}",
            f"location {wh} {{",
            f"    proxy_pass http://{up};",
            "    proxy_set_header Host $host;",
            "    proxy_set_header X-Real-IP $remote_addr;",
            "    proxy_set_header X-Telegram-Bot-Api-Secret-Token $http_x_telegram_bot_api_secret_token;",
            "    proxy_read_timeout 60s;",
            "}",
        ]
    )


def write_http_routes_for_instance(
    instance_id: str,
    *,
    slug: str,
    port: int = 8000,
    enabled: bool = True,
) -> dict:
    """Phase 3: /p/<slug> → upstream for HTTP-public hosts."""
    out: dict = {"instance_id": instance_id, "slug": slug, "enabled": enabled}
    try:
        from lumen.engine.services.hosting.ingress import write_http_path_route
        out["route"] = write_http_path_route(
            instance_id=instance_id,
            slug=slug,
            upstream_port=int(port or 8000),
            enabled=enabled,
        )
        out["ok"] = True
        out["public_url"] = (out["route"] or {}).get("public_url") or ""
    except Exception as exc:
        out["ok"] = False
        out["error"] = type(exc).__name__
        logger.exception("write_http_routes failed")
    return out


def gateway_mode() -> str:

    if (os.environ.get("TBE_TRAEFIK_DYNAMIC_DIR") or "").strip():
        return "traefik"
    if (os.environ.get("TBE_CADDY_DYNAMIC_DIR") or "").strip():
        return "caddy"
    return (os.environ.get("TBE_HOST_GATEWAY") or "path_api").strip().lower()


__all__ = [
    "write_routes_for_instance",
    "remove_routes_for_instance",
    "nginx_snippet",
    "gateway_mode",
    "write_http_routes_for_instance",
]
