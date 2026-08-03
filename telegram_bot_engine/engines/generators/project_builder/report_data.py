"""
Initialized Project / Build Report data model (Specification 030).

First engine that actually scaffolds the project (folders + empty files)
according to the intelligent plan — without writing business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SOURCE_CODE_PLAN = "code_generation_plan"
SOURCE_STRUCTURE = "project_structure_blueprint"
SOURCE_MODULE_ARCH = "module_architecture_blueprint"
SOURCE_COMPONENT_ARCH = "component_architecture_blueprint"
SOURCE_STRATEGY = "generation_strategy_blueprint"
SOURCE_SESSION = "generation_session_report"

ALL_SOURCES = (
    SOURCE_CODE_PLAN,
    SOURCE_STRUCTURE,
    SOURCE_MODULE_ARCH,
    SOURCE_COMPONENT_ARCH,
    SOURCE_STRATEGY,
    SOURCE_SESSION,
)

ENTRY_FOLDER = "folder"
ENTRY_FILE = "file"

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

CONFLICT_MISSING_PATH = "missing_path"
CONFLICT_DUPLICATE_PATH = "duplicate_path"
CONFLICT_STRUCTURE_MISMATCH = "structure_mismatch"
CONFLICT_EMPTY_PROJECT = "empty_project"

ALL_CONFLICT_TYPES = (
    CONFLICT_MISSING_PATH, CONFLICT_DUPLICATE_PATH,
    CONFLICT_STRUCTURE_MISMATCH, CONFLICT_EMPTY_PROJECT,
)

RULE_PROJECT_INITIALIZED = "project_initialized"
RULE_FOLDERS_CREATED = "folders_created"
RULE_FILES_CREATED = "files_created"
RULE_NO_DUPLICATES = "no_duplicates"
RULE_MANIFEST_COMPLETE = "manifest_complete"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_PROJECT_INITIALIZED,
    RULE_FOLDERS_CREATED,
    RULE_FILES_CREATED,
    RULE_NO_DUPLICATES,
    RULE_MANIFEST_COMPLETE,
    RULE_SUFFICIENT_CONFIDENCE,
)

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_DISABLED = "disabled"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)


@dataclass
class ProjectIdentity:
    project_id: str = ""
    project_name: str = ""
    version: str = "0.1.0"
    created_at: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "version": self.version,
            "created_at": self.created_at,
            "description": self.description,
        }


@dataclass
class ScaffoldEntry:
    entry_id: str
    path: str
    entry_type: str = ENTRY_FILE  # folder | file
    purpose: str = ""
    blueprint_ref: str = ""
    created: bool = True
    relationships: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "path": self.path,
            "entry_type": self.entry_type,
            "purpose": self.purpose,
            "blueprint_ref": self.blueprint_ref,
            "created": self.created,
            "relationships": list(self.relationships),
        }


@dataclass
class ProjectManifest:
    folders: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    relationships: List[Dict[str, str]] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "folders": list(self.folders),
            "files": list(self.files),
            "relationships": [dict(r) for r in self.relationships],
            "dependencies": list(self.dependencies),
        }


@dataclass
class ProjectRegistry:
    modules: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)
    configurations: List[str] = field(default_factory=list)
    resources: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "modules": list(self.modules),
            "components": list(self.components),
            "interfaces": list(self.interfaces),
            "configurations": list(self.configurations),
            "resources": list(self.resources),
            "services": list(self.services),
        }


@dataclass
class BuildLogEntry:
    entry_id: str
    timestamp: str
    action: str
    path: str = ""
    result: str = "ok"
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "path": self.path,
            "result": self.result,
            "reason": self.reason,
        }


@dataclass
class BuildConflict:
    conflict_id: str
    conflict_type: str
    severity: str = SEVERITY_HIGH
    message: str = ""
    affected_paths: List[str] = field(default_factory=list)
    resolution_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "message": self.message,
            "affected_paths": list(self.affected_paths),
            "resolution_hint": self.resolution_hint,
        }


@dataclass
class BuildFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "quality"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


@dataclass
class CacheInfo:
    status: str = CACHE_MISS
    key: str = ""
    created_at: str = ""
    hits: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "key": self.key,
            "created_at": self.created_at,
            "hits": self.hits,
        }


@dataclass
class BuildProvenance:
    engine_name: str = "project_builder"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "sources_used": list(self.sources_used),
            "sources_missing": list(self.sources_missing),
            "generated_at": self.generated_at,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
        }


@dataclass
class InitializedProjectReport:
    """Complete Initialized Project / Build Report."""

    report_id: str = ""
    identity: ProjectIdentity = field(default_factory=ProjectIdentity)
    entries: List[ScaffoldEntry] = field(default_factory=list)
    manifest: ProjectManifest = field(default_factory=ProjectManifest)
    registry: ProjectRegistry = field(default_factory=ProjectRegistry)
    logs: List[BuildLogEntry] = field(default_factory=list)
    conflicts: List[BuildConflict] = field(default_factory=list)
    findings: List[BuildFinding] = field(default_factory=list)
    folder_count: int = 0
    file_count: int = 0
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: BuildProvenance = field(default_factory=BuildProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "identity": self.identity.to_dict(),
            "entries": [e.to_dict() for e in self.entries],
            "manifest": self.manifest.to_dict(),
            "registry": self.registry.to_dict(),
            "logs": [l.to_dict() for l in self.logs],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "findings": [f.to_dict() for f in self.findings],
            "folder_count": self.folder_count,
            "file_count": self.file_count,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_CODE_PLAN", "SOURCE_STRUCTURE", "SOURCE_MODULE_ARCH",
    "SOURCE_COMPONENT_ARCH", "SOURCE_STRATEGY", "SOURCE_SESSION", "ALL_SOURCES",
    "ENTRY_FOLDER", "ENTRY_FILE",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW",
    "CONFLICT_MISSING_PATH", "CONFLICT_DUPLICATE_PATH",
    "CONFLICT_STRUCTURE_MISMATCH", "CONFLICT_EMPTY_PROJECT", "ALL_CONFLICT_TYPES",
    "RULE_PROJECT_INITIALIZED", "RULE_FOLDERS_CREATED", "RULE_FILES_CREATED",
    "RULE_NO_DUPLICATES", "RULE_MANIFEST_COMPLETE", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "ProjectIdentity", "ScaffoldEntry", "ProjectManifest", "ProjectRegistry",
    "BuildLogEntry", "BuildConflict", "BuildFinding",
    "CacheInfo", "BuildProvenance", "InitializedProjectReport",
]
