"""Intelligent Environment Configuration Engine package (Specification 051)."""

from .environment_config_engine import EnvironmentConfigEngine
from .report_data import (
    EnvironmentConfigReport, EnvironmentProfile, EnvVariable, HealthCheck,
    ConfigBackup, EnvScore, EnvFinding, CacheInfo, EnvProvenance,
    ALL_SOURCES, ALL_QUALITY_RULES, ALL_VERDICTS, ALL_ENVIRONMENTS,
    VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY,
)

__all__ = [
    "EnvironmentConfigEngine",
    "EnvironmentConfigReport",
    "EnvironmentProfile",
    "EnvVariable",
    "HealthCheck",
    "ConfigBackup",
    "EnvScore",
    "EnvFinding",
    "CacheInfo",
    "EnvProvenance",
    "ALL_SOURCES",
    "ALL_QUALITY_RULES",
    "ALL_VERDICTS",
    "ALL_ENVIRONMENTS",
    "VERDICT_READY",
    "VERDICT_READY_WITH_WARNINGS",
    "VERDICT_NOT_READY",
]
