"""Hosting = runtime."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from ..core.state import DeploymentStatus

@dataclass(frozen=True)
class HostingBoundary:
    deployment_id: str
    project_id: str
    status: DeploymentStatus = DeploymentStatus.STOPPED
    endpoint: Optional[str] = None
    process_ref: Optional[str] = None
