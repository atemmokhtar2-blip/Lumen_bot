"""
ArtifactStore — the ONLY store for stage outputs.

Rules (enforced):
  - Every key should be registered (BUILTIN_KEYS).
  - Artifacts are stage outputs, never long-lived domain state.
  - Role write enforcement: generation cannot write planning keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Generic, Iterable, Optional, Type, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ArtifactKey(Generic[T]):
    name: str
    value_type: Type[T]
    description: str = ""
    write_role: Optional[str] = None


def _k(name: str, desc: str = "", write_role: Optional[str] = None) -> ArtifactKey:
    return ArtifactKey(name=name, value_type=object, description=desc, write_role=write_role)


KEY_ANALYSIS_REPORT = _k("analysis_report", "Request analysis report", "planning")
KEY_PROJECT_BLUEPRINT = _k("project_blueprint", "Validated project blueprint", "planning")
KEY_PROJECT_STRUCTURE_BLUEPRINT = _k("project_structure_blueprint", "Structure blueprint", "planning")
KEY_PROJECT_STRUCTURE_MAP = _k("project_structure_map", "Structure map", "generation")
KEY_FILE_GENERATION_PLAN = _k("file_generation_plan", "File generation plan", "planning")
KEY_DEPENDENCY_RESOLUTION_REPORT = _k("dependency_resolution_report", "Dependency resolution", "generation")
KEY_FILE_SYSTEM_REPORT = _k("file_system_report", "Filesystem materialisation", "generation")
KEY_WORKSPACE_MANAGEMENT_REPORT = _k("workspace_management_report", "Workspace report", "generation")
KEY_BLUEPRINT_VALIDATION_REPORT = _k("blueprint_validation_report", "Single blueprint validation", "validation")
KEY_BLUEPRINT_VALIDATION_REPORTS = _k("blueprint_validation_reports", "Blueprint validation list", "validation")
KEY_OUTPUT_VALIDATION_REPORTS = _k("output_validation_reports", "Output validation list", "validation")
KEY_COMPONENT_REGISTRY = _k("component_registry", "Detected components", "generation")
KEY_CLASS_GENERATION_REPORT = _k("class_generation_report", "Class generation", "generation")
KEY_GIT_OPERATIONS_REPORT = _k("git_operations_report", "Git ops result", "generation")
KEY_REPOSITORY_MANAGEMENT_REPORT = _k("repository_management_report", "Repo management", "generation")
KEY_LIVE_DEPLOYMENT_REPORT = _k("live_deployment_report", "Live deploy", "runtime")
KEY_FINAL_PROJECT = _k("final_project", "Packaged project descriptor", "generation")
KEY_GENERATED_FILES = _k("generated_files", "List of generated files", "generation")
KEY_BLUEPRINT = _k("blueprint", "Legacy/composed blueprint", "planning")
KEY_INTENT = _k("intent", "Parsed intent", "planning")
KEY_USER_INTENT = _k("user_intent", "User intent object", "planning")
KEY_CONVERSATION_HISTORY = _k("conversation_history", "Chat history for run", None)
KEY_GEMINI_UNDERSTANDING = _k("gemini_understanding", "Understanding payload", "planning")
KEY_PREVIOUS_STRICT_SPEC = _k("previous_strict_spec", "Prior strict spec", None)
KEY_SPEC_BACKENDS = _k("spec_backends", "Spec backends", "planning")
KEY_SPEC_CORE_CAPABILITIES = _k("spec_core_capabilities", "Capabilities", "planning")
KEY_QA_SUMMARY = _k("qa_summary", "QA summary", "validation")
KEY_REPAIR_DIRECTIVE = _k("repair_directive", "Repair directive", "validation")
KEY_LIVE_BOT_TOKEN = _k("live_bot_token", "Bot token for live run", "runtime")
KEY_LIVE_OWNER_USER_ID = _k("live_owner_user_id", "Owner user id", "runtime")
KEY_REPO_CONTRACT = _k("repo_contract", "Structural repo contract", None)
KEY_REPO_INTELLIGENCE = _k("repo_intelligence", "DERIVED only — never source of truth", None)

_ALL_KEYS = [
    KEY_ANALYSIS_REPORT, KEY_PROJECT_BLUEPRINT, KEY_PROJECT_STRUCTURE_BLUEPRINT,
    KEY_PROJECT_STRUCTURE_MAP, KEY_FILE_GENERATION_PLAN, KEY_DEPENDENCY_RESOLUTION_REPORT,
    KEY_FILE_SYSTEM_REPORT, KEY_WORKSPACE_MANAGEMENT_REPORT, KEY_BLUEPRINT_VALIDATION_REPORT,
    KEY_BLUEPRINT_VALIDATION_REPORTS, KEY_OUTPUT_VALIDATION_REPORTS, KEY_COMPONENT_REGISTRY,
    KEY_CLASS_GENERATION_REPORT, KEY_GIT_OPERATIONS_REPORT, KEY_REPOSITORY_MANAGEMENT_REPORT,
    KEY_LIVE_DEPLOYMENT_REPORT, KEY_FINAL_PROJECT, KEY_GENERATED_FILES, KEY_BLUEPRINT,
    KEY_INTENT, KEY_USER_INTENT, KEY_CONVERSATION_HISTORY, KEY_GEMINI_UNDERSTANDING,
    KEY_PREVIOUS_STRICT_SPEC, KEY_SPEC_BACKENDS, KEY_SPEC_CORE_CAPABILITIES, KEY_QA_SUMMARY,
    KEY_REPAIR_DIRECTIVE, KEY_LIVE_BOT_TOKEN, KEY_LIVE_OWNER_USER_ID, KEY_REPO_CONTRACT,
    KEY_REPO_INTELLIGENCE,
]
BUILTIN_KEYS: Dict[str, ArtifactKey] = {k.name: k for k in _ALL_KEYS}


class ArtifactStoreError(KeyError):
    """Unregistered key or role violation."""


class ArtifactStore:
    def __init__(
        self,
        *,
        strict: bool = True,
        extra_keys: Optional[Iterable[ArtifactKey]] = None,
        writer_role: Optional[str] = None,
    ) -> None:
        self._data: Dict[str, Any] = {}
        self._keys: Dict[str, ArtifactKey] = dict(BUILTIN_KEYS)
        if extra_keys:
            for k in extra_keys:
                self._keys[k.name] = k
        self._strict = strict
        self._writer_role = writer_role

    def register_key(self, key: ArtifactKey) -> None:
        if not key.name:
            raise ValueError("ArtifactKey.name must be non-empty")
        self._keys[key.name] = key

    def set_writer_role(self, role: Optional[str]) -> None:
        self._writer_role = role

    def set(self, key: str | ArtifactKey, value: Any) -> None:
        name = key.name if isinstance(key, ArtifactKey) else key
        if not name:
            raise ValueError("artifact key must be non-empty")
        meta = self._keys.get(name)
        if meta is None:
            if self._strict:
                raise ArtifactStoreError(
                    f"Unregistered artifact key '{name}'. "
                    f"Register it in core/artifact_store.py BUILTIN_KEYS."
                )
            self._data[name] = value
            return
        if (
            meta.write_role == "planning"
            and self._writer_role in ("generation", "runtime")
        ):
            raise ArtifactStoreError(
                f"Role violation: engine role '{self._writer_role}' cannot "
                f"write planning artifact '{name}'."
            )
        self._data[name] = value

    def get(self, key: str | ArtifactKey, default: Any = None) -> Any:
        name = key.name if isinstance(key, ArtifactKey) else key
        return self._data.get(name, default)

    def has(self, key: str | ArtifactKey) -> bool:
        name = key.name if isinstance(key, ArtifactKey) else key
        return name in self._data

    def require(self, key: str | ArtifactKey) -> Any:
        name = key.name if isinstance(key, ArtifactKey) else key
        if name not in self._data:
            raise ArtifactStoreError(f"Required artifact missing: '{name}'")
        return self._data[name]

    def keys_present(self) -> list[str]:
        return sorted(self._data.keys())

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._data)

    def clear(self) -> None:
        self._data.clear()


__all__ = [
    "ArtifactKey", "ArtifactStore", "ArtifactStoreError", "BUILTIN_KEYS",
    "KEY_ANALYSIS_REPORT", "KEY_PROJECT_BLUEPRINT", "KEY_PROJECT_STRUCTURE_BLUEPRINT",
    "KEY_PROJECT_STRUCTURE_MAP", "KEY_FILE_GENERATION_PLAN", "KEY_DEPENDENCY_RESOLUTION_REPORT",
    "KEY_FILE_SYSTEM_REPORT", "KEY_WORKSPACE_MANAGEMENT_REPORT", "KEY_BLUEPRINT_VALIDATION_REPORT",
    "KEY_BLUEPRINT_VALIDATION_REPORTS", "KEY_OUTPUT_VALIDATION_REPORTS", "KEY_COMPONENT_REGISTRY",
    "KEY_CLASS_GENERATION_REPORT", "KEY_GIT_OPERATIONS_REPORT", "KEY_REPOSITORY_MANAGEMENT_REPORT",
    "KEY_LIVE_DEPLOYMENT_REPORT", "KEY_FINAL_PROJECT", "KEY_GENERATED_FILES", "KEY_BLUEPRINT",
    "KEY_INTENT", "KEY_USER_INTENT", "KEY_REPO_CONTRACT", "KEY_REPO_INTELLIGENCE",
]
