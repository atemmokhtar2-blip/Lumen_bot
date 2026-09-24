"""Hosting domain models (HostInstance / HostResult).

Extracted from service.py so the control-plane service stays focused on
lifecycle operations while types remain importable without loading the full
HostingService implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...schemas.error_contract import ErrorContract


@dataclass
class HostInstance:
    instance_id: str
    user_id: int
    project_path: str
    tenant_id: str = ""  # B2B tenant binding — required for multi-tenant isolation
    entry_point: str = ""
    bot_username: str = ""
    status: str = "stopped"  # starting | running | stopped | failed
    deployment_id: str = ""
    sandbox_backend: str = ""  # firecracker only in production
    pid: int | None = None
    started_at: float = 0.0
    last_error: str = ""
    last_diagnosis: dict[str, Any] = field(default_factory=dict)
    token_fp: str = ""  # sha256[:16] of bot token — never store raw token
    public_base_url: str = ""  # stable ingress URL (Traefik/Caddy by name, not random port)
    webhook_public_url: str = ""  # https://…/v1/hooks/telegram/{instance_id}
    internal_port: int = 0  # logical service port for reverse-proxy (not random host map)
    platform: str = "telegram"  # telegram | discord | whatsapp | http
    host_mode: str = "telegram_webhook"  # telegram_webhook | http_public
    project_kind: str = ""  # telegram_bot | web_site | web_api | …
    language: str = "python"  # LanguageRuntime
    slug: str = ""  # URL slug under LUMEN_PUBLIC_BASE
    public_url: str = ""  # browser-openable URL (Phase 3)
    health_path: str = ""  # e.g. /health for HTTP apps
    health_url: str = ""  # public_url + health_path
    cpu_quota: float = 0.25
    memory_mb: int = 128
    version_ref: str = ""  # git commit sha of project snapshot at deploy
    last_health_at: float = 0.0


@dataclass
class HostResult:
    ok: bool
    message: str
    instance: HostInstance | None = None
    error_contract: ErrorContract | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_user_text(self) -> str:
        """User-facing hosting result — official Telegram HTML cards."""
        from lumen.bot.telegram_text import html_bullets, html_card

        details: list[str] = []
        if self.message:
            details.append(str(self.message)[:400])
        if self.instance:
            inst = self.instance
            details.append(f"الحالة: {inst.status}")
            if getattr(inst, "public_url", "") or getattr(inst, "public_base_url", ""):
                details.append(f"الرابط: {getattr(inst, 'public_url', None) or inst.public_base_url}")
            if getattr(inst, "host_mode", ""):
                details.append(f"وضع الاستضافة: {inst.host_mode}")
            if inst.bot_username:
                details.append(f"البوت: @{inst.bot_username}")
            if inst.instance_id:
                details.append(f"المعرّف: {inst.instance_id}")
            if inst.pid:
                details.append(f"PID: {inst.pid}")
            if inst.project_path:
                details.append(f"المسار: {inst.project_path}")
            if inst.last_error:
                details.append(f"آخر خطأ: {inst.last_error[:200]}")
        sections: list[tuple[str, str]] = [
            ("النتيجة", html_bullets(details) if details else ("نجاح" if self.ok else "فشل")),
        ]
        if self.error_contract and self.error_contract.primary:
            sections.append(("تشخيص", self.error_contract.to_user_summary()[:800]))
        return html_card(
            "استضافة",
            sections,
            subtitle="نجاح العملية" if self.ok else "تعذّر الإكمال",
        )

