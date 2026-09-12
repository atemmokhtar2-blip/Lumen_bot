"""Immutable domain models for ready-made bot templates."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

# Stable public ids only: snake_case, 2–64 chars
_TEMPLATE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_INSTANCE_ID_RE = re.compile(r"^tpl_[a-f0-9]{8,32}$")


def validate_template_id(value: str) -> str:
    tid = (value or "").strip()
    if not _TEMPLATE_ID_RE.match(tid):
        raise ValueError(f"invalid_template_id:{tid!r}")
    return tid


class TemplateLaunchMode(str, Enum):
    TRIAL = "trial"
    PERMANENT = "permanent"

    @classmethod
    def parse(cls, raw: object) -> "TemplateLaunchMode":
        s = str(raw or "").strip().lower()
        try:
            return cls(s)
        except ValueError as exc:
            raise ValueError(f"invalid_mode:{s!r}") from exc


class TemplateInstanceStatus(str, Enum):
    PREPARING = "preparing"
    RUNNING = "running"
    STOPPED = "stopped"
    EXPIRED = "expired"
    FAILED = "failed"

    @classmethod
    def parse(cls, raw: object) -> "TemplateInstanceStatus":
        s = str(raw or "").strip().lower()
        try:
            return cls(s)
        except ValueError as exc:
            raise ValueError(f"invalid_status:{s!r}") from exc


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    """Catalog entry shown on the templates surface."""

    id: str
    title: str
    description: str
    tags: tuple[str, ...] = ()
    asset_key: str = ""
    short_id: str = ""  # ≤6 chars for Telegram signed callback arg
    enabled: bool = True
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_template_id(self.id))
        title = (self.title or "").strip()
        if not title:
            raise ValueError("template_title_required")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", (self.description or "").strip())
        tags = tuple(str(t).strip() for t in (self.tags or ()) if str(t).strip())
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "asset_key", (self.asset_key or self.id).strip())
        sid = (self.short_id or "").strip().lower() or self.id[:6]
        # Telegram signed arg hard-cap is 12; keep short_id ≤ 6
        sid = re.sub(r"[^a-z0-9]", "", sid)[:6] or self.id[:6]
        object.__setattr__(self, "short_id", sid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "asset_key": self.asset_key,
            "short_id": self.short_id,
            "enabled": self.enabled,
            "version": int(self.version),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "TemplateSpec":
        if not isinstance(raw, Mapping):
            raise ValueError("template_spec_not_mapping")
        tags_raw = raw.get("tags") or []
        if not isinstance(tags_raw, (list, tuple)):
            tags_raw = []
        return cls(
            id=str(raw.get("id") or ""),
            title=str(raw.get("title") or ""),
            description=str(raw.get("description") or ""),
            tags=tuple(str(t) for t in tags_raw),
            asset_key=str(raw.get("asset_key") or ""),
            short_id=str(raw.get("short_id") or ""),
            enabled=bool(raw.get("enabled", True)),
            version=int(raw.get("version") or 1),
        )


@dataclass(slots=True)
class TemplateInstance:
    """User-owned template slot (quota unit). Tokens never stored here."""

    instance_id: str
    user_id: int
    template_id: str
    mode: TemplateLaunchMode
    status: TemplateInstanceStatus = TemplateInstanceStatus.PREPARING
    started_at: float = 0.0
    expires_at: float = 0.0
    trial_minutes: int = 0
    host_instance_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.template_id = validate_template_id(self.template_id)
        if int(self.user_id) <= 0:
            raise ValueError("invalid_user_id")
        if not (self.instance_id or "").strip():
            raise ValueError("instance_id_required")
        if not isinstance(self.mode, TemplateLaunchMode):
            self.mode = TemplateLaunchMode.parse(self.mode)
        if not isinstance(self.status, TemplateInstanceStatus):
            self.status = TemplateInstanceStatus.parse(self.status)
        self.trial_minutes = max(0, int(self.trial_minutes or 0))
        self.meta = dict(self.meta or {})
        # Strip any accidental secret-looking keys
        for k in list(self.meta.keys()):
            lk = str(k).lower()
            if any(x in lk for x in ("token", "secret", "password", "pat", "api_key")):
                self.meta.pop(k, None)

    def is_active(self, now: float) -> bool:
        if self.status not in {
            TemplateInstanceStatus.PREPARING,
            TemplateInstanceStatus.RUNNING,
        }:
            return False
        if self.expires_at > 0 and self.expires_at <= now:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "user_id": int(self.user_id),
            "template_id": self.template_id,
            "mode": self.mode.value,
            "status": self.status.value,
            "started_at": float(self.started_at),
            "expires_at": float(self.expires_at),
            "trial_minutes": int(self.trial_minutes),
            "host_instance_id": self.host_instance_id,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "TemplateInstance":
        if not isinstance(raw, Mapping):
            raise ValueError("instance_not_mapping")
        return cls(
            instance_id=str(raw.get("instance_id") or "").strip(),
            user_id=int(raw.get("user_id") or 0),
            template_id=str(raw.get("template_id") or ""),
            mode=TemplateLaunchMode.parse(raw.get("mode")),
            status=TemplateInstanceStatus.parse(
                raw.get("status") or TemplateInstanceStatus.PREPARING.value
            ),
            started_at=float(raw.get("started_at") or 0.0),
            expires_at=float(raw.get("expires_at") or 0.0),
            trial_minutes=int(raw.get("trial_minutes") or 0),
            host_instance_id=str(raw.get("host_instance_id") or "").strip(),
            meta=dict(raw.get("meta") or {}) if isinstance(raw.get("meta"), dict) else {},
        )


__all__ = [
    "validate_template_id",
    "TemplateLaunchMode",
    "TemplateInstanceStatus",
    "TemplateSpec",
    "TemplateInstance",
]
