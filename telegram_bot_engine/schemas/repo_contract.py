"""Repository intelligence contracts — compatible with scanner + intelligence layers."""
from __future__ import annotations

from typing import Any, Optional

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    # Minimal fallback if pydantic missing
    from dataclasses import dataclass, field, asdict

    def _dump(obj: Any) -> Any:
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, list):
            return [_dump(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _dump(v) for k, v in obj.items()}
        if hasattr(obj, "__dict__"):
            return {k: _dump(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
        return str(obj)

    class BaseModel:  # type: ignore
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self, mode: str = "python", **kwargs):
            return _dump(self)

        def model_copy(self, *, update: dict | None = None, deep: bool = False):
            data = self.model_dump()
            data.update(update or {})
            return self.__class__(**data)

    def Field(default=None, default_factory=None, **kwargs):  # type: ignore
        if default_factory is not None:
            return default_factory()
        return default


class FileEntry(BaseModel):
    path: str = ""
    size: int = 0
    kind: str = ""


class EntryPoint(BaseModel):
    path: str = ""
    reason: str = ""
    score: float = 0.0


class DetectedCommand(BaseModel):
    name: str = ""
    source_file: str = ""
    evidence: str = ""
    registration: str = ""


class DetectedHandler(BaseModel):
    kind: str = ""
    name: str = ""
    source_file: str = ""


class EnvVarInfo(BaseModel):
    name: str = ""
    source_file: str = ""


class FunctionInfo(BaseModel):
    name: str = ""
    file: str = ""
    is_async: bool = False
    decorators: list[str] = Field(default_factory=list)


class ClassInfo(BaseModel):
    name: str = ""
    file: str = ""
    bases: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    kind: str = ""


class LayerInfo(BaseModel):
    name: str = ""
    path: str = ""
    file_count: int = 0
    role: str = ""


class ModuleInfo(BaseModel):
    path: str = ""
    name: str = ""
    imports: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    lines: int = 0
    role: str = ""


class DeepFunction(BaseModel):
    file: str = ""
    name: str = ""
    qualname: str = ""
    lineno: int = 0
    is_async: bool = False
    calls: list[str] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)


class CodeGraph(BaseModel):
    modules_indexed: int = 0
    function_count: int = 0
    class_count: int = 0
    call_edge_count: int = 0
    lines_covered: int = 0
    index_ms: float = 0.0
    syntax_errors: list[str] = Field(default_factory=list)
    functions: list[DeepFunction] = Field(default_factory=list)
    call_graph_sample: dict[str, list[str]] = Field(default_factory=dict)
    module_function_counts: dict[str, int] = Field(default_factory=dict)


class RepoCapability(BaseModel):
    name: str = ""
    path: str = ""
    kind: str = ""
    confidence: float = 0.5
    detail: str = ""


class RepoRisk(BaseModel):
    title: str = ""
    severity: str = "medium"
    detail: str = ""
    path: str = ""


class RepoGap(BaseModel):
    title: str = ""
    detail: str = ""
    suggested_action: str = ""


class DependencyGap(BaseModel):
    module: str = ""
    package: str = ""
    severity: str = "medium"
    detail: str = ""


class RepoIntelligence(BaseModel):
    summary: str = ""
    capabilities: list[RepoCapability] = Field(default_factory=list)
    risks: list[RepoRisk] = Field(default_factory=list)
    gaps: list[RepoGap] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    dependency_gaps: list[DependencyGap] = Field(default_factory=list)
    host_readiness: float = 0.0
    next_actions: list[str] = Field(default_factory=list)
    change_surface: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class RepoContract(BaseModel):
    """Structural + intelligence contract produced by understand_repo."""

    # Scanner (v3) fields
    root_path: str = ""
    repo_name: str = ""
    remote_url: str = ""
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    architecture_style: str = ""
    entry_points: list[EntryPoint] = Field(default_factory=list)
    commands: list[DetectedCommand] = Field(default_factory=list)
    handlers: list[DetectedHandler] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    layers: list[LayerInfo] = Field(default_factory=list)
    key_classes: list[ClassInfo] = Field(default_factory=list)
    key_functions: list[FunctionInfo] = Field(default_factory=list)
    modules_sample: list[ModuleInfo] = Field(default_factory=list)
    env_vars: list[EnvVarInfo] = Field(default_factory=list)
    data_models: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    engines: list[str] = Field(default_factory=list)
    file_count: int = 0
    python_file_count: int = 0
    total_lines: int = 0
    top_files: list[FileEntry] = Field(default_factory=list)
    top_dirs: list[str] = Field(default_factory=list)
    is_telegram_bot: bool = False
    is_generation_engine: bool = False
    confidence: float = 0.0
    summary: str = ""
    architecture_summary: str = ""
    notes: list[str] = Field(default_factory=list)
    quality_signals: dict[str, Any] = Field(default_factory=dict)
    raw_stats: dict[str, Any] = Field(default_factory=dict)
    code_graph: Optional[CodeGraph] = None

    # Intelligence / legacy aliases
    root: str = ""
    name: str = ""
    language: str = "python"
    files: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    capabilities: list[RepoCapability] = Field(default_factory=list)
    risks: list[RepoRisk] = Field(default_factory=list)
    gaps: list[RepoGap] = Field(default_factory=list)
    intelligence: Optional[RepoIntelligence] = None
    integrations: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    message: str = ""
    schema_version: str = "3.0"

    def model_dump(self, mode: str = "python", **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        try:
            return super().model_dump(mode=mode, **kwargs)  # type: ignore[misc]
        except Exception:
            # Fallback for non-pydantic BaseModel stub
            return {k: getattr(self, k, None) for k in self.__dict__ if not k.startswith("_")}


def safe_contract_dict(contract: Any) -> dict[str, Any]:
    """Never raise on None / partial contracts — used after clone understand step."""
    if contract is None:
        return {"ok": False, "message": "no_contract"}
    try:
        if hasattr(contract, "model_dump"):
            return contract.model_dump(mode="json")
    except Exception:
        pass
    try:
        from dataclasses import asdict, is_dataclass
        if is_dataclass(contract):
            return asdict(contract)
    except Exception:
        pass
    try:
        return dict(getattr(contract, "__dict__", {}) or {})
    except Exception:
        return {"ok": False, "message": "contract_serialize_failed"}
