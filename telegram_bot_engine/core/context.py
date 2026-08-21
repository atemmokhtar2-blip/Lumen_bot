"""
GenerationContext — pipeline carrier with enforced separation.

artifacts : ArtifactStore (typed stage outputs — primary)
metadata  : RunMetadata   (diagnostics only)
run_state : RunState      (long-lived — NOT an artifact)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .artifact_store import ArtifactStore, ArtifactStoreError
from .metadata import RunMetadata
from .state import RunState, RunStatus

if TYPE_CHECKING:
    from ..configuration.config import Configuration
    from ..blueprint.blueprint import Blueprint


@dataclass
class GenerationContext:
    request: str
    config: "Configuration"
    work_dir: Path
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    blueprint: Optional["Blueprint"] = None
    artefacts: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_files: List[str] = field(default_factory=list)

    _store: ArtifactStore = field(default=None, repr=False)  # type: ignore[assignment]
    _run_metadata: RunMetadata = field(default=None, repr=False)  # type: ignore[assignment]
    _run_state: Optional[RunState] = field(default=None, repr=False)
    _active_role: Optional[str] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._store is None:
            object.__setattr__(self, "_store", ArtifactStore(strict=False))
        if self._run_metadata is None:
            object.__setattr__(self, "_run_metadata", RunMetadata(run_id=self.run_id))
        elif not self._run_metadata.run_id:
            self._run_metadata.run_id = self.run_id
        if self._run_state is None:
            object.__setattr__(
                self,
                "_run_state",
                RunState(
                    run_id=self.run_id,
                    status=RunStatus.PENDING,
                    request_summary=(self.request or "")[:200],
                ),
            )
        for k, v in list(self.artefacts.items()):
            try:
                self._store.set(k, v)
            except ArtifactStoreError:
                self._store._data[k] = v  # noqa: SLF001

    def set_active_role(self, role: Optional[str]) -> None:
        self._active_role = role
        self._store.set_writer_role(role)

    def set(self, key: str, value: Any) -> None:
        self._store.set(key, value)
        self.artefacts[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        if self._store.has(key):
            return self._store.get(key, default)
        return self.artefacts.get(key, default)

    def has(self, key: str) -> bool:
        return self._store.has(key) or key in self.artefacts

    def require(self, key: str) -> Any:
        return self._store.require(key)

    def track_file(self, path: str) -> None:
        if path not in self.created_files:
            self.created_files.append(path)

    def attach_blueprint(self, blueprint: "Blueprint") -> None:
        self.blueprint = blueprint

    @property
    def has_blueprint(self) -> bool:
        return self.blueprint is not None

    @property
    def artifact_store(self) -> ArtifactStore:
        return self._store

    @property
    def run_metadata(self) -> RunMetadata:
        return self._run_metadata

    @property
    def run_state(self) -> Optional[RunState]:
        return self._run_state

    def mark_running(self) -> None:
        if self._run_state:
            self._run_state.mark_running()

    def mark_succeeded(self) -> None:
        if self._run_state:
            self._run_state.mark_succeeded()

    def mark_failed(self, error: str) -> None:
        if self._run_state:
            self._run_state.mark_failed(error)


__all__ = ["GenerationContext"]
