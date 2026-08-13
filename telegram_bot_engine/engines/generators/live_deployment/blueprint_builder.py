"""Blueprint builder for Live Deployment report shell."""

from __future__ import annotations

from .report_data import LiveDeploymentReport, VERDICT_NOT_READY


class BlueprintBuilder:
    def build_empty(self, project_path: str = "") -> LiveDeploymentReport:
        return LiveDeploymentReport(
            project_path=project_path,
            verdict=VERDICT_NOT_READY,
            passed=False,
        )
