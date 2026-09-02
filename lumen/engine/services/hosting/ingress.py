"""Stable ingress for hosted bots — product webhook router (Traefik/Caddy).

Each permanent host gets a name-based route:
  Host(`{instance_id}.{TBE_HOST_BASE_DOMAIN}`) → API backend
    PathPrefix(`/v1/hooks/telegram/{instance_id}`) preferred when API is shared.

Config:
  TBE_HOST_BASE_DOMAIN=hosts.example.com
  TBE_TRAEFIK_DYNAMIC_DIR=/etc/traefik/dynamic
  TBE_CADDY_DYNAMIC_DIR=/etc/caddy/dynamic
  TBE_INGRESS_BACKEND_URL=http://127.0.0.1:8080   # API process
  TBE_PUBLIC_URL_SCHEME=https
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("tbe.hosting.ingress")

_SAFE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}$")


def base_domain() -> str:
    return (os.environ.get("TBE_HOST_BASE_DOMAIN") or "").strip().lower().rstrip(".")


def public_url_scheme() -> str:
    return (os.environ.get("TBE_PUBLIC_URL_SCHEME") or "https").strip() or "https"


def public_url_for_instance(instance_id: str) -> str:
    domain = base_domain()
    iid = (instance_id or "").strip()
    if not domain or not iid or not _SAFE.match(iid):
        return ""
    return f"{public_url_scheme()}://{iid}.{domain}"


def api_backend_url() -> str:
    return (
        (os.environ.get("TBE_INGRESS_BACKEND_URL") or "").strip()
        or (os.environ.get("TBE_INGRESS_DEFAULT_BACKEND") or "").strip()
        or "http://127.0.0.1:8080"
    )


def traefik_dynamic_dir() -> Path | None:
    raw = (os.environ.get("TBE_TRAEFIK_DYNAMIC_DIR") or "").strip()
    return Path(raw) if raw else None


def caddy_dynamic_dir() -> Path | None:
    raw = (os.environ.get("TBE_CADDY_DYNAMIC_DIR") or "").strip()
    return Path(raw) if raw else None


def webhook_path(instance_id: str) -> str:
    return f"/v1/hooks/telegram/{instance_id}"


def write_traefik_route(
    *,
    instance_id: str,
    backend_url: str = "",
    enabled: bool = True,
) -> dict[str, Any]:
    """Write Traefik file-provider YAML: Host + PathPrefix → API webhook endpoint."""
    domain = base_domain()
    public = public_url_for_instance(instance_id)
    result: dict[str, Any] = {
        "public_base_url": public,
        "domain": domain,
        "written": False,
        "path": "",
        "webhook_path": webhook_path(instance_id),
    }
    ddir = traefik_dynamic_dir()
    if not ddir:
        return result
    try:
        ddir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("traefik dynamic dir: %s", exc)
        return result

    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "-", instance_id)[:64]
    path = ddir / f"lumen-host-{safe_id}.yaml"
    result["path"] = str(path)
    if not enabled:
        try:
            if path.is_file():
                path.unlink()
        except Exception:
            pass
        return result

    svc_url = (backend_url or api_backend_url()).rstrip("/")
    # Prefer path-based on shared API host; also Host-based when domain set
    lines = [
        "# lumen host webhook router — generated; do not edit",
        "http:",
        "  routers:",
        f"    lumen-wh-{safe_id}:",
        f'      rule: "PathPrefix(`{webhook_path(instance_id)}`)"',
        "      entryPoints:",
        "        - websecure",
        "        - web",
        f"      service: lumen-api-{safe_id}",
        "      priority: 100",
    ]
    if domain and public:
        host = f"{instance_id}.{domain}".lower()
        lines += [
            f"    lumen-host-{safe_id}:",
            f'      rule: "Host(`{host}`) && PathPrefix(`{webhook_path(instance_id)}`)"',
            "      entryPoints:",
            "        - websecure",
            f"      service: lumen-api-{safe_id}",
            "      tls: {}",
            "      priority: 200",
        ]
    lines += [
        "  services:",
        f"    lumen-api-{safe_id}:",
        "      loadBalancer:",
        "        servers:",
        f'          - url: "{svc_url}"',
        "        passHostHeader: true",
        "",
    ]
    try:
        path.write_text("\n".join(lines), encoding="utf-8")
        result["written"] = True
        result["backend"] = svc_url
    except Exception as exc:
        logger.warning("write traefik route failed: %s", exc)
    return result


def remove_traefik_route(instance_id: str) -> None:
    write_traefik_route(instance_id=instance_id, enabled=False)


def write_caddy_route(
    *,
    instance_id: str,
    backend_url: str = "",
    enabled: bool = True,
) -> dict[str, Any]:
    domain = base_domain()
    public = public_url_for_instance(instance_id)
    result: dict[str, Any] = {
        "public_base_url": public,
        "written": False,
        "path": "",
        "webhook_path": webhook_path(instance_id),
    }
    ddir = caddy_dynamic_dir()
    if not ddir:
        return result
    try:
        ddir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return result
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "-", instance_id)[:64]
    path = ddir / f"lumen-host-{safe_id}.caddy"
    result["path"] = str(path)
    if not enabled:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return result
    svc = (backend_url or api_backend_url()).rstrip("/")
    wh = webhook_path(instance_id)
    # Caddyfile fragment — reverse_proxy to API
    body_lines = [
        f"# lumen host {instance_id}",
        f"handle_path {wh}* {{",
        f"\treverse_proxy {svc}",
        "}",
    ]
    if domain:
        host = f"{instance_id}.{domain}".lower()
        body_lines = [
            f"# lumen host {instance_id}",
            f"{host} {{",
            f"\thandle {wh}* {{",
            f"\t\treverse_proxy {svc}",
            "\t}",
            "}",
        ]
    try:
        path.write_text("\n".join(body_lines) + "\n", encoding="utf-8")
        result["written"] = True
        result["backend"] = svc
    except Exception as exc:
        logger.warning("write caddy route failed: %s", exc)
    return result


def remove_caddy_route(instance_id: str) -> None:
    write_caddy_route(instance_id=instance_id, enabled=False)


__all__ = [
    "base_domain",
    "public_url_for_instance",
    "api_backend_url",
    "webhook_path",
    "write_traefik_route",
    "remove_traefik_route",
    "write_caddy_route",
    "remove_caddy_route",
    "traefik_dynamic_dir",
    "caddy_dynamic_dir",
]
