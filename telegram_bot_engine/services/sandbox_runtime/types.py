"""Sandbox runtime types — isolated execution of generated bots."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SandboxSpec:
    """What to run inside the sandbox."""

    project_path: str
    bot_token: str
    user_id: int = 0
    service_name: str = "generated-bot"
    env_vars: dict[str, str] = field(default_factory=dict)
    memory: str = ""
    cpus: str = ""
    pids: str = ""


@dataclass
class SandboxHandle:
    """Opaque handle for a running sandbox instance."""

    backend: str
    deployment_id: str
    container_or_vm_id: str = ""
    status: str = "unknown"  # starting|running|stopped|failed
    message: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {"running", "starting"} and bool(self.deployment_id)


@dataclass
class SandboxProbe:
    """Capability probe for a backend."""

    name: str
    available: bool
    reason: str = ""
    strength: int = 0  # higher = stronger isolation
