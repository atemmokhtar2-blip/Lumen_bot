"""Live Deployment & Smart Testing Engine — Specification 065.

Import heavy engine lazily so docker_process_driver / LocalProcessDriver can load
even when optional pieces of the engine graph fail.
"""

from __future__ import annotations

from typing import Any

from .report_data import (
    LiveDeploymentReport,
    TokenValidationResult,
    DeploymentStatus,
    HealthCheckResult,
    FunctionalTestCase,
    RuntimeErrorRecord,
    DeploymentFinding,
    ALL_SOURCES,
    ALL_QUALITY_RULES,
    ALL_VERDICTS,
    MIN_QUALITY_SCORE,
    VERDICT_READY,
    VERDICT_READY_WITH_WARNINGS,
    VERDICT_NOT_READY,
)

__all__ = [
    "LiveDeploymentEngine",
    "LiveDeploymentReport",
    "TokenValidationResult",
    "DeploymentStatus",
    "HealthCheckResult",
    "FunctionalTestCase",
    "RuntimeErrorRecord",
    "DeploymentFinding",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "MIN_QUALITY_SCORE",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
    "DockerProcessDriver",
    "LocalProcessDriver",
    "docker_available",
]


def __getattr__(name: str) -> Any:
    if name == "LiveDeploymentEngine":
        from .live_deployment_engine import LiveDeploymentEngine
        return LiveDeploymentEngine
    if name == "DockerProcessDriver":
        from .docker_process_driver import DockerProcessDriver
        return DockerProcessDriver
    if name == "LocalProcessDriver":
        from .local_process_driver import LocalProcessDriver
        return LocalProcessDriver
    if name == "docker_available":
        from .docker_process_driver import docker_available
        return docker_available
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
