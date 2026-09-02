"""Stable ingress for hosted bots — Traefik file-provider (name-based, not random ports).

Problem: mapping each bot to a random host port breaks when the VM/container is
recreated. Solution: a single entrypoint (Traefik/Caddy) routes by Host header
to the backend identified by instance_id.

Config:
  TBE_HOST_BASE_DOMAIN=hosts.example.com
  TBE_TRAEFIK_DYNAMIC_DIR=/etc/traefik/dynamic   # optional; writes YAML when set
  TBE_PUBLIC_URL_SCHEME=https

This module does not require Traefik to be installed on the API process; it
emits the contract (URL + optional file) operators wire to their proxy.
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


def public_url_for_instance(instance_id: str) -> str:
    """Stable public base URL for an instance (empty if domain not configured)."""
    domain = base_domain()
    iid = (instance_id or "").strip()
    if not domain or not iid or not _SAFE.match(iid.replace("_", "-")):
        # still form a deterministic relative key when domain missing
        if not domain:
            return ""
    host = f"{iid}.{domain}".lower()
    scheme = (os.environ.get("TBE_PUBLIC_URL_SCHEME") or "https").strip() or "https"
    return f"{scheme}://{host}"


def traefik_dynamic_dir() -> Path | None:
    raw = (os.environ.get("TBE_TRAEFIK_DYNAMIC_DIR") or "").strip()
    if not raw:
        return None
    return Path(raw)


def write_traefik_route(
    *,
    instance_id: str,
    backend_url: str = "",
    enabled: bool = True,
) -> dict[str, Any]:
    """Write or remove a Traefik file-provider route for this instance.

    backend_url: internal URL (e.g. http://10.0.0.5:8080) when webhook/HTTP
    path is used. For polling-only bots the route may still exist as a
    status/health endpoint later.
    """
    domain = base_domain()
    public = public_url_for_instance(instance_id)
    result: dict[str, Any] = {
        "public_base_url": public,
        "domain": domain,
        "written": False,
        "path": "",
    }
    ddir = traefik_dynamic_dir()
    if not ddir or not domain:
        return result
    try:
        ddir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("traefik dynamic dir: %s", exc)
        return result

    path = ddir / f"lumen-host-{instance_id}.yaml"
    result["path"] = str(path)
    if not enabled:
        try:
            if path.is_file():
                path.unlink()
        except Exception:
            pass
        return result

    # Traefik v2/v3 file provider — Host rule by stable name
    host = f"{instance_id}.{domain}".lower()
    service_url = backend_url or (os.environ.get("TBE_INGRESS_DEFAULT_BACKEND") or "http://127.0.0.1:9")
    yaml = "\n".join([
        "# lumen host route — do not edit by hand",
        "http:",
        "  routers:",
        f"    lumen-{instance_id}:",
        f"      rule: \"Host(`{host}`)\"",
        "      entryPoints:",
        "        - websecure",
        f"      service: lumen-{instance_id}",
        "      tls: {}",
        "  services:",
        f"    lumen-{instance_id}:",
        "      loadBalancer:",
        "        servers:",
        f'          - url: "{service_url}"',
        "",
    ])
    try:
        path.write_text(yaml, encoding="utf-8")
        result["written"] = True
    except Exception as exc:
        logger.warning("write traefik route failed: %s", exc)
    return result


def remove_traefik_route(instance_id: str) -> None:
    write_traefik_route(instance_id=instance_id, enabled=False)


def caddy_dynamic_dir() -> Path | None:
    raw = (os.environ.get("TBE_CADDY_DYNAMIC_DIR") or "").strip()
    return Path(raw) if raw else None


def write_caddy_route(
    *,
    instance_id: str,
    backend_url: str = "",
    enabled: bool = True,
) -> dict[str, Any]:
    """Caddy JSON/snippet by hostname — alternative to Traefik when TBE_CADDY_DYNAMIC_DIR set."""
    domain = base_domain()
    public = public_url_for_instance(instance_id)
    result: dict[str, Any] = {"public_base_url": public, "written": False, "path": ""}
    ddir = caddy_dynamic_dir()
    if not ddir or not domain:
        return result
    try:
        ddir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return result
    path = ddir / f"lumen-host-{instance_id}.caddy"
    result["path"] = str(path)
    if not enabled:
        try:
            path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except Exception:
            try:
                if path.is_file():
                    path.unlink()
            except Exception:
                pass
        return result
    host = f"{instance_id}.{domain}".lower()
    service_url = backend_url or (os.environ.get("TBE_INGRESS_DEFAULT_BACKEND") or "http://127.0.0.1:9")
    body = f"{host} {{\n\treverse_proxy {service_url}\n}}\n"
    try:
        path.write_text(body, encoding="utf-8")
        result["written"] = True
    except Exception as exc:
        logger.warning("caddy route write failed: %s", exc)
    return result



__all__ = [
    "base_domain",
    "public_url_for_instance",
    "write_traefik_route",
    "remove_traefik_route",
]
