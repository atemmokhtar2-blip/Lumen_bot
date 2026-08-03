"""Tolerant data readers for Interface & Contract Planning (Spec 023)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ....core.context import GenerationContext

_log = logging.getLogger("engine.interface_contract_planning.data_readers")


def _safe(a: Any) -> Dict[str, Any]:
    if hasattr(a, "to_dict"):
        return a.to_dict()
    if isinstance(a, dict):
        return a
    return {"value": str(a)}


@dataclass
class ExecutionPlanData:
    available: bool = False
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ProjectStructureData:
    available: bool = False
    files: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ModuleArchitectureData:
    available: bool = False
    modules: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ComponentArchitectureData:
    available: bool = False
    components: List[Dict[str, Any]] = field(default_factory=list)
    interfaces: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


@dataclass
class ArchitectureDecisionData:
    available: bool = False
    architecture_style: str = ""
    raw: Optional[Dict[str, Any]] = None
    error: str = ""


class ExecutionPlanReader:
    ARTEFACT_KEY = "execution_plan"
    def read(self, ctx: GenerationContext) -> ExecutionPlanData:
        d = ExecutionPlanData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                d.error = f"missing {self.ARTEFACT_KEY}"; return d
            raw = _safe(a); d.raw, d.available = raw, True
            d.tasks = raw.get("tasks") or []
        except Exception as e:
            d.error = str(e)
        return d


class ProjectStructureReader:
    ARTEFACT_KEY = "project_structure_blueprint"
    def read(self, ctx: GenerationContext) -> ProjectStructureData:
        d = ProjectStructureData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                d.error = f"missing {self.ARTEFACT_KEY}"; return d
            raw = _safe(a); d.raw, d.available = raw, True
            d.files = raw.get("files") or []
        except Exception as e:
            d.error = str(e)
        return d


class ModuleArchitectureReader:
    ARTEFACT_KEY = "module_architecture_blueprint"
    def read(self, ctx: GenerationContext) -> ModuleArchitectureData:
        d = ModuleArchitectureData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                d.error = f"missing {self.ARTEFACT_KEY}"; return d
            raw = _safe(a); d.raw, d.available = raw, True
            d.modules = raw.get("modules") or []
        except Exception as e:
            d.error = str(e)
        return d


class ComponentArchitectureReader:
    ARTEFACT_KEY = "component_architecture_blueprint"
    def read(self, ctx: GenerationContext) -> ComponentArchitectureData:
        d = ComponentArchitectureData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                d.error = f"missing {self.ARTEFACT_KEY}"; return d
            raw = _safe(a); d.raw, d.available = raw, True
            d.components = raw.get("components") or []
            d.interfaces = raw.get("interfaces") or []
        except Exception as e:
            d.error = str(e)
        return d


class ArchitectureDecisionReader:
    ARTEFACT_KEY = "architecture_decision_report"
    def read(self, ctx: GenerationContext) -> ArchitectureDecisionData:
        d = ArchitectureDecisionData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                d.error = f"missing {self.ARTEFACT_KEY}"; return d
            raw = _safe(a); d.raw, d.available = raw, True
            d.architecture_style = raw.get("architecture_style") or raw.get("style") or ""
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "ExecutionPlanData", "ProjectStructureData", "ModuleArchitectureData",
    "ComponentArchitectureData", "ArchitectureDecisionData",
    "ExecutionPlanReader", "ProjectStructureReader", "ModuleArchitectureReader",
    "ComponentArchitectureReader", "ArchitectureDecisionReader",
]
