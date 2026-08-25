"""
BlueprintBuilder — Specification 020
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .report_data import (
    ProjectStructureBlueprint,
    FolderNode,
    FileDescriptor,
    ModuleMapping,
    FileDependency,
    StructureConflict,
    StructureFinding,
    CacheInfo,
    StructureProvenance,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    VERDICT_NOT_READY,
)

_log = logging.getLogger("engine.project_structure_planning.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        root_name: str,
        folders: List[FolderNode],
        files: List[FileDescriptor],
        modules: List[ModuleMapping],
        dependencies: List[FileDependency],
        conflicts: List[StructureConflict],
        sources_used: List[str],
        sources_missing: List[str],
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> ProjectStructureBlueprint:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        provenance = StructureProvenance(
            engine_name="project_structure_planning",
            engine_version="1.0.0",
            sources_used=list(sources_used),
            sources_missing=list(sources_missing),
            generated_at=datetime.now(timezone.utc).isoformat(),
            confidence=confidence,
            confidence_level=conf_level,
        )
        folder_tree = self._build_tree(folders)

        bp = ProjectStructureBlueprint(
            blueprint_id=str(uuid.uuid4()),
            root_name=root_name,
            folders=folders,
            files=files,
            modules=modules,
            dependencies=dependencies,
            conflicts=conflicts,
            findings=[],
            folder_tree=folder_tree,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=provenance,
            is_empty=len(files) == 0,
        )
        _log.info("BlueprintBuilder produced blueprint %s (%d folders, %d files)",
                  bp.blueprint_id[:8], len(folders), len(files))
        return bp

    def _build_tree(self, folders: List[FolderNode]) -> Dict[str, Any]:
        by_id = {f.folder_id: f for f in folders}
        def node(fid: str) -> Dict[str, Any]:
            f = by_id[fid]
            return {
                "name": f.name,
                "path": f.path,
                "purpose": f.purpose,
                "children": [node(c) for c in f.children if c in by_id],
            }
        roots = [f for f in folders if f.parent_id is None]
        if not roots:
            return {}
        return node(roots[0].folder_id)


__all__ = ["BlueprintBuilder"]
