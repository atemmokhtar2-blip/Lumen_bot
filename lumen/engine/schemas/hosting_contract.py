"""Hosting plane contracts — trust-boundary validation (Pydantic).

Industry pattern: validate untrusted / persisted dicts at the door before
they become HostInstance. Aligns with Firecracker production discipline:
explicit lifecycle status, no silent weak fields, fingerprint never raw token.

See also:
  - lumen.engine.services.hosting.contract (frozen field lists / gates)
  - lumen.engine.services.hosting.service.HostInstance (runtime dataclass)
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Lifecycle statuses observed in HostInstance / SandboxHandle.
# AWS Lambda MicroVMs use PENDING/RUNNING/SUSPENDED/TERMINATED; we map the
# product surface already implemented in Lumen (no suspend yet — Phase 4+).
HostStatus = Literal["starting", "running", "stopped", "failed", "unknown"]

SandboxBackendName = Literal["firecracker", "gvisor", "dind", "docker", ""]


class HostInstanceRecord(BaseModel):
    """Validated persistence / API shape for a permanent host instance.

    Required at the door: instance_id, user_id, project_path, status.
    Optional fields match HostInstance dataclass defaults.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    instance_id: str = Field(..., min_length=1, max_length=128)
    user_id: int = Field(..., ge=0)
    project_path: str = Field(..., min_length=1)
    entry_point: str = ""
    bot_username: str = ""
    status: str = "stopped"
    deployment_id: str = ""
    sandbox_backend: str = ""
    pid: Optional[int] = None
    started_at: float = 0.0
    last_error: str = ""
    last_diagnosis: dict[str, Any] = Field(default_factory=dict)
    token_fp: str = Field(default="", max_length=64)

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v: Any) -> str:
        s = str(v or "stopped").strip().lower() or "stopped"
        # Accept deploy_* aliases used in scale path, map to product surface
        if s in {"deploy_running", "running"}:
            return "running"
        if "fail" in s:
            return "failed"
        if s in {"starting", "running", "stopped", "failed", "unknown"}:
            return s
        return s  # keep unknown custom states but as string (worker may extend)

    @field_validator("token_fp", mode="before")
    @classmethod
    def _reject_raw_token_shape(cls, v: Any) -> str:
        """Refuse values that look like full Telegram bot tokens in token_fp."""
        s = str(v or "").strip()
        if not s:
            return ""
        # Telegram tokens look like 123456:ABC... — must never land in token_fp
        if ":" in s and len(s) > 30:
            raise ValueError("token_fp must be fingerprint only, not raw bot token")
        return s[:64]

    @field_validator("last_diagnosis", mode="before")
    @classmethod
    def _diagnosis_dict(cls, v: Any) -> dict[str, Any]:
        if v is None or v == "":
            return {}
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            import json

            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def to_host_instance(self) -> Any:
        """Build runtime HostInstance dataclass from validated record."""
        from lumen.engine.services.hosting.service import HostInstance

        return HostInstance(
            instance_id=self.instance_id,
            user_id=int(self.user_id),
            project_path=self.project_path,
            entry_point=self.entry_point or "",
            bot_username=self.bot_username or "",
            status=self.status or "stopped",
            deployment_id=self.deployment_id or "",
            sandbox_backend=self.sandbox_backend or "",
            pid=self.pid,
            started_at=float(self.started_at or 0.0),
            last_error=self.last_error or "",
            last_diagnosis=dict(self.last_diagnosis or {}),
            token_fp=self.token_fp or "",
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "HostInstanceRecord":
        """Validate a DB/API dict at the trust boundary."""
        return cls.model_validate(row)


class HostPlane(BaseModel):
    """Plane identity — TRIAL vs PERMANENT (documentation + API clarity)."""

    model_config = ConfigDict(frozen=True)

    plane_id: Literal["TRIAL_CHAT", "PERMANENT_HOST"]
    module: str
    long_running: bool


TRIAL_PLANE = HostPlane(
    plane_id="TRIAL_CHAT",
    module="lumen.engine.services.live_runner",
    long_running=False,
)
PERMANENT_PLANE = HostPlane(
    plane_id="PERMANENT_HOST",
    module="lumen.engine.services.hosting",
    long_running=True,
)


__all__ = [
    "HostInstanceRecord",
    "HostStatus",
    "SandboxBackendName",
    "HostPlane",
    "TRIAL_PLANE",
    "PERMANENT_PLANE",
]
