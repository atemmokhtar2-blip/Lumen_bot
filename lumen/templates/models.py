"""Template system domain models (Phase 0).

Bounded context: ready-made bot templates. No Telegram UI and no hosting
side-effects live here — only data shapes shared by policy, store, and later
adapters.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TemplateLaunchMode(str, Enum):
    """How the user launches a template instance."""

    TRIAL = "trial"  # temporary minutes (hard cap 50)
    PERMANENT = "permanent"  # up to 30 days for free-tier template instances


class TemplateInstanceStatus(str, Enum):
    PREPARING = "preparing"
    RUNNING = "running"
    STOPPED = "stopped"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass(frozen=True)
class TemplateSpec:
    """One catalog entry — description shown under each template card."""

    id: str
    title: str
    description: str  # Arabic: what the bot does
    tags: tuple[str, ...] = ()
    # Optional relative asset key under templates/data or generator id (Phase 3+)
    asset_key: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "asset_key": self.asset_key,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "TemplateSpec | None":
        if not isinstance(raw, dict):
            return None
        tid = str(raw.get("id") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not tid or not title:
            return None
        tags_raw = raw.get("tags") or []
        tags = tuple(str(t).strip() for t in tags_raw if str(t).strip())
        return cls(
            id=tid,
            title=title,
            description=str(raw.get("description") or "").strip(),
            tags=tags,
            asset_key=str(raw.get("asset_key") or "").strip(),
            enabled=bool(raw.get("enabled", True)),
        )


@dataclass
class TemplateInstance:
    """A user-owned running (or scheduled) template bot slot."""

    instance_id: str
    user_id: int
    template_id: str
    mode: TemplateLaunchMode
    status: TemplateInstanceStatus = TemplateInstanceStatus.PREPARING
    # Unix seconds; 0 means unset
    started_at: float = 0.0
    expires_at: float = 0.0
    trial_minutes: int = 0  # only for TRIAL
    host_instance_id: str = ""  # filled when hosting adapter wires (Phase 3+)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["mode"] = self.mode.value if isinstance(self.mode, TemplateLaunchMode) else str(self.mode)
        d["status"] = self.status.value if isinstance(self.status, TemplateInstanceStatus) else str(self.status)
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "TemplateInstance | None":
        if not isinstance(raw, dict):
            return None
        iid = str(raw.get("instance_id") or "").strip()
        tid = str(raw.get("template_id") or "").strip()
        try:
            uid = int(raw.get("user_id") or 0)
        except (TypeError, ValueError):
            return None
        if not iid or not tid or uid <= 0:
            return None
        mode_raw = str(raw.get("mode") or TemplateLaunchMode.TRIAL.value).strip().lower()
        try:
            mode = TemplateLaunchMode(mode_raw)
        except ValueError:
            mode = TemplateLaunchMode.TRIAL
        st_raw = str(raw.get("status") or TemplateInstanceStatus.PREPARING.value).strip().lower()
        try:
            status = TemplateInstanceStatus(st_raw)
        except ValueError:
            status = TemplateInstanceStatus.PREPARING
        try:
            started_at = float(raw.get("started_at") or 0.0)
        except (TypeError, ValueError):
            started_at = 0.0
        try:
            expires_at = float(raw.get("expires_at") or 0.0)
        except (TypeError, ValueError):
            expires_at = 0.0
        try:
            trial_minutes = int(raw.get("trial_minutes") or 0)
        except (TypeError, ValueError):
            trial_minutes = 0
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        return cls(
            instance_id=iid,
            user_id=uid,
            template_id=tid,
            mode=mode,
            status=status,
            started_at=started_at,
            expires_at=expires_at,
            trial_minutes=max(0, trial_minutes),
            host_instance_id=str(raw.get("host_instance_id") or "").strip(),
            meta=dict(meta),
        )


__all__ = [
    "TemplateLaunchMode",
    "TemplateInstanceStatus",
    "TemplateSpec",
    "TemplateInstance",
]
