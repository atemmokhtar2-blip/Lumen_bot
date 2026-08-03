"""
StructureValidator — Specification 020

Validates the assembled folder tree and file list for duplicates,
unused folders, name collisions and circular references.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Set

from .report_data import (
    FolderNode,
    FileDescriptor,
    FileDependency,
    StructureConflict,
    CONFLICT_DUPLICATE_FILE,
    CONFLICT_DUPLICATE_FOLDER,
    CONFLICT_UNUSED_FOLDER,
    CONFLICT_NAME_COLLISION,
    CONFLICT_CIRCULAR_STRUCTURE,
    CONFLICT_ORPHAN_FILE,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.project_structure_planning.structure_validator")


class StructureValidator:
    """Detects structural problems in the blueprint."""

    def __init__(self) -> None:
        self.conflicts: List[StructureConflict] = []

    def validate(
        self,
        folders: List[FolderNode],
        files: List[FileDescriptor],
        dependencies: List[FileDependency],
    ) -> List[StructureConflict]:
        self.conflicts = []
        self._check_duplicate_folders(folders)
        self._check_duplicate_files(files)
        self._check_name_collisions(files)
        self._check_unused_folders(folders, files)
        self._check_orphan_files(folders, files)
        self._check_circular_structure(dependencies)
        _log.info("StructureValidator found %d conflicts", len(self.conflicts))
        return self.conflicts

    def _check_duplicate_folders(self, folders: List[FolderNode]) -> None:
        seen: Dict[str, str] = {}
        for f in folders:
            key = f.path.lower()
            if key in seen:
                self.conflicts.append(StructureConflict(
                    conflict_id=f"dup_folder_{f.folder_id}",
                    conflict_type=CONFLICT_DUPLICATE_FOLDER,
                    severity=SEVERITY_HIGH,
                    message=f"Duplicate folder path '{f.path}'.",
                    affected_paths=[f.path, seen[key]],
                    resolution_hint="Ensure every folder path is unique.",
                ))
            else:
                seen[key] = f.path

    def _check_duplicate_files(self, files: List[FileDescriptor]) -> None:
        seen: Dict[str, str] = {}
        for f in files:
            key = f.path.lower()
            if key in seen:
                self.conflicts.append(StructureConflict(
                    conflict_id=f"dup_file_{f.file_id}",
                    conflict_type=CONFLICT_DUPLICATE_FILE,
                    severity=SEVERITY_CRITICAL,
                    message=f"Duplicate file path '{f.path}'.",
                    affected_paths=[f.path, seen[key]],
                    resolution_hint="Ensure every file path is unique.",
                ))
            else:
                seen[key] = f.path

    def _check_name_collisions(self, files: List[FileDescriptor]) -> None:
        by_name: Dict[str, List[str]] = defaultdict(list)
        for f in files:
            by_name[f.name.lower()].append(f.path)
        for name, paths in by_name.items():
            if len(paths) > 1:
                # Same name in different folders is usually OK; flag only if same folder segment
                self.conflicts.append(StructureConflict(
                    conflict_id=f"name_coll_{name}",
                    conflict_type=CONFLICT_NAME_COLLISION,
                    severity=SEVERITY_MEDIUM,
                    message=f"File name '{name}' appears in multiple locations.",
                    affected_paths=paths,
                    resolution_hint="Consider more specific names if confusion is likely.",
                ))

    def _check_unused_folders(self, folders: List[FolderNode], files: List[FileDescriptor]) -> None:
        used_folders = {f.folder_id for f in files if f.folder_id}
        # Also count folders that have children
        parents = {f.parent_id for f in folders if f.parent_id}
        for folder in folders:
            if folder.folder_id == "root":
                continue
            if folder.folder_id not in used_folders and folder.folder_id not in parents:
                if not folder.children:
                    self.conflicts.append(StructureConflict(
                        conflict_id=f"unused_{folder.folder_id}",
                        conflict_type=CONFLICT_UNUSED_FOLDER,
                        severity=SEVERITY_MEDIUM,
                        message=f"Folder '{folder.path}' contains no files and no children.",
                        affected_paths=[folder.path],
                        resolution_hint="Remove the unused folder or assign files to it.",
                    ))

    def _check_orphan_files(self, folders: List[FolderNode], files: List[FileDescriptor]) -> None:
        known = {f.folder_id for f in folders}
        for f in files:
            if f.folder_id and f.folder_id not in known:
                self.conflicts.append(StructureConflict(
                    conflict_id=f"orphan_{f.file_id}",
                    conflict_type=CONFLICT_ORPHAN_FILE,
                    severity=SEVERITY_HIGH,
                    message=f"File '{f.path}' references unknown folder '{f.folder_id}'.",
                    affected_paths=[f.path],
                    resolution_hint="Assign the file to a valid folder.",
                ))

    def _check_circular_structure(self, dependencies: List[FileDependency]) -> None:
        graph: Dict[str, List[str]] = defaultdict(list)
        for d in dependencies:
            graph[d.from_file_id].append(d.to_file_id)

        visited: Set[str] = set()
        stack: Set[str] = set()

        def dfs(node: str, path: List[str]) -> None:
            if node in stack:
                cycle = path[path.index(node):] + [node]
                self.conflicts.append(StructureConflict(
                    conflict_id=f"cycle_{'_'.join(cycle[:3])}",
                    conflict_type=CONFLICT_CIRCULAR_STRUCTURE,
                    severity=SEVERITY_CRITICAL,
                    message=f"Circular file dependency: {' → '.join(cycle)}",
                    affected_paths=cycle,
                    resolution_hint="Break the cycle by removing or reordering one dependency.",
                ))
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            for nb in graph.get(node, []):
                dfs(nb, path + [nb])
            stack.discard(node)

        for start in list(graph.keys()):
            if start not in visited:
                dfs(start, [start])


__all__ = ["StructureValidator"]
