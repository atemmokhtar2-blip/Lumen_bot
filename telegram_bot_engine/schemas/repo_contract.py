"""Repository intelligence contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RepoCapability:
    name: str = ""
    path: str = ""
    kind: str = ""
    confidence: float = 0.5
    detail: str = ""


@dataclass
class RepoRisk:
    title: str = ""
    severity: str = "medium"
    detail: str = ""
    path: str = ""


@dataclass
class RepoGap:
    title: str = ""
    detail: str = ""
    suggested_action: str = ""


@dataclass
class RepoIntelligence:
    summary: str = ""
    capabilities: list[RepoCapability] = field(default_factory=list)
    risks: list[RepoRisk] = field(default_factory=list)
    gaps: list[RepoGap] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    tech_stack: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class RepoContract:
    root: str = ""
    name: str = ""
    language: str = "python"
    files: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    capabilities: list[RepoCapability] = field(default_factory=list)
    risks: list[RepoRisk] = field(default_factory=list)
    gaps: list[RepoGap] = field(default_factory=list)
    intelligence: Optional[RepoIntelligence] = None
    integrations: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    message: str = ""
