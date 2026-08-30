"""
Deployment Provider Interface — Specification 065.

Railway is a driver, not a hard dependency of the engine core.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from .report_data import DeploymentStatus


class DeploymentProvider(ABC):
    """Abstract deployment backend."""

    name: str = "abstract"

    @abstractmethod
    def deploy(
        self,
        project_path: str,
        *,
        env_vars: Optional[Dict[str, str]] = None,
        service_name: str = "generated-bot",
    ) -> DeploymentStatus:
        """Create/update deployment and return status."""

    @abstractmethod
    def status(self, deployment_id: str) -> DeploymentStatus:
        """Fetch current deployment status."""

    @abstractmethod
    def stop(self, deployment_id: str) -> DeploymentStatus:
        """Stop a running deployment."""

    @abstractmethod
    def restart(self, deployment_id: str, *, bot_token: str = "",
                project_path: str = "",
                env_vars: Optional[Dict[str, str]] = None) -> DeploymentStatus:
        """Smart restart: stop the old deployment, then start a fresh one with
        the *same* project_path + bot_token so edited code runs immediately.

        The caller (engine layer) retrieves the sealed token from
        SecretsManager and the project_path from the deployment registry, then
        passes both here.  When bot_token/project_path are omitted, the driver
        stops the old deployment but cannot start a new one (returns STOPPED).
        """

    @abstractmethod
    def logs(self, deployment_id: str, *, limit: int = 50) -> List[str]:
        """Return recent log lines (secrets must already be redacted by caller)."""
