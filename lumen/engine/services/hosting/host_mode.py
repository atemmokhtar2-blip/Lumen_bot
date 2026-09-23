"""Unified hosting modes for PERMANENT_HOST (Phase 3 — VPS-ready).

host_mode:
  telegram_webhook  — long-running bot + Telegram webhook ingress
  http_public       — HTTP app (FastAPI/site) behind reverse proxy

URL schemes (LUMEN_URL_SCHEME):
  path       — https://host.lumen.example/p/<slug>/     (default, option A)
  subdomain  — https://<slug>.lumen.example/            (option B)

Env:
  LUMEN_PUBLIC_BASE   e.g. https://host.lumen.example  (required for public URLs)
  LUMEN_URL_SCHEME    path | subdomain
  LUMEN_HEALTH_PATH   default /health
"""
from __future__ import annotations

import os
import re
from enum import Enum
from typing import Any


class HostMode(str, Enum):
    TELEGRAM_WEBHOOK = "telegram_webhook"
    HTTP_PUBLIC = "http_public"


class UrlScheme(str, Enum):
    PATH = "path"
    SUBDOMAIN = "subdomain"


_SLUG_RE = re.compile(r"[^a-z0-9\-]+")


def parse_host_mode(value: str | None) -> HostMode | None:
    v = (value or "").strip().lower()
    if not v:
        return None
    for m in HostMode:
        if m.value == v:
            return m
    aliases = {
        "telegram": HostMode.TELEGRAM_WEBHOOK,
        "bot": HostMode.TELEGRAM_WEBHOOK,
        "webhook": HostMode.TELEGRAM_WEBHOOK,
        "http": HostMode.HTTP_PUBLIC,
        "web": HostMode.HTTP_PUBLIC,
        "site": HostMode.HTTP_PUBLIC,
        "api": HostMode.HTTP_PUBLIC,
    }
    return aliases.get(v)


def host_mode_for_kind(project_kind: str | None) -> HostMode:
    k = (project_kind or "").strip().lower()
    if k in {"web_site", "web_api"}:
        return HostMode.HTTP_PUBLIC
    if k in {"cli_app", "library", "general_app"}:
        # artifact-first; still may run as http if user deploys as API later
        return HostMode.HTTP_PUBLIC if k == "general_app" else HostMode.HTTP_PUBLIC
    return HostMode.TELEGRAM_WEBHOOK


def normalize_slug(raw: str, *, fallback: str = "app") -> str:
    s = (raw or "").strip().lower().replace("_", "-").replace(" ", "-")
    s = _SLUG_RE.sub("-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if not s:
        s = fallback
    return s[:48]


def public_base() -> str:
    return (os.getenv("LUMEN_PUBLIC_BASE") or "").strip().rstrip("/")


def url_scheme() -> UrlScheme:
    raw = (os.getenv("LUMEN_URL_SCHEME") or "path").strip().lower()
    if raw in {"subdomain", "sub", "wildcard"}:
        return UrlScheme.SUBDOMAIN
    return UrlScheme.PATH


def health_path() -> str:
    h = (os.getenv("LUMEN_HEALTH_PATH") or "/health").strip() or "/health"
    if not h.startswith("/"):
        h = "/" + h
    return h


def allocate_public_url(
    *,
    slug: str,
    instance_id: str = "",
    scheme: UrlScheme | None = None,
) -> dict[str, Any]:
    """Allocate public_url + health_url for a hosted project.

    Without LUMEN_PUBLIC_BASE returns empty public_url (honest: not published yet).
    """
    base = public_base()
    slug_n = normalize_slug(slug or instance_id or "app")
    sch = scheme or url_scheme()
    hp = health_path()

    if not base:
        return {
            "slug": slug_n,
            "public_url": "",
            "health_url": "",
            "health_path": hp,
            "url_scheme": sch.value,
            "base_configured": False,
            "message": "LUMEN_PUBLIC_BASE not set — configure VPS base domain to expose public URLs",
        }

    if sch is UrlScheme.SUBDOMAIN:
        # https://host.example → https://slug.host.example
        # strip scheme for host part
        if "://" in base:
            proto, rest = base.split("://", 1)
            host = rest.split("/")[0]
            public_url = f"{proto}://{slug_n}.{host}/"
        else:
            public_url = f"https://{slug_n}.{base}/"
    else:
        public_url = f"{base}/p/{slug_n}/"

    health_url = public_url.rstrip("/") + hp
    return {
        "slug": slug_n,
        "public_url": public_url,
        "health_url": health_url,
        "health_path": hp,
        "url_scheme": sch.value,
        "base_configured": True,
        "message": "",
    }


def registry_fields(
    *,
    host_mode: HostMode,
    project_kind: str,
    slug: str,
    instance_id: str = "",
) -> dict[str, Any]:
    """Fields to persist on HostInstance for unified plane."""
    urls = allocate_public_url(slug=slug, instance_id=instance_id)
    return {
        "host_mode": host_mode.value,
        "project_kind": (project_kind or "").strip().lower(),
        "slug": urls["slug"],
        "public_url": urls["public_url"],
        "public_base_url": urls["public_url"],  # alias for legacy field
        "health_path": urls["health_path"],
        "health_url": urls["health_url"],
        "url_scheme": urls["url_scheme"],
        "base_configured": urls["base_configured"],
    }


__all__ = [
    "HostMode",
    "UrlScheme",
    "parse_host_mode",
    "host_mode_for_kind",
    "normalize_slug",
    "public_base",
    "url_scheme",
    "health_path",
    "allocate_public_url",
    "registry_fields",
]
