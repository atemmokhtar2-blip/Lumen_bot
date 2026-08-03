"""
ArchitectureValidator — Specification 021

Detects duplicate modules, overlapping responsibilities and incomplete modules.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import List

from .report_data import (
    ModuleDescriptor,
    ArchitectureConflict,
    CONFLICT_DUPLICATE_MODULE,
    CONFLICT_OVERLAPPING_RESPONSIBILITY,
    CONFLICT_INCOMPLETE_MODULE,
    CONFLICT_MISSING_INTERFACE,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.module_architecture_planning.architecture_validator")


class ArchitectureValidator:
    def __init__(self) -> None:
        self.conflicts: List[ArchitectureConflict] = []

    def validate(self, modules: List[ModuleDescriptor]) -> List[ArchitectureConflict]:
        self.conflicts = []
        self._check_duplicates(modules)
        self._check_overlapping(modules)
        self._check_incomplete(modules)
        self._check_missing_interfaces(modules)
        _log.info("ArchitectureValidator found %d conflicts", len(self.conflicts))
        return self.conflicts

    def _check_duplicates(self, modules: List[ModuleDescriptor]) -> None:
        seen = {}
        for m in modules:
            key = m.module_id.lower()
            if key in seen:
                self.conflicts.append(ArchitectureConflict(
                    conflict_id=f"dup_{m.module_id}",
                    conflict_type=CONFLICT_DUPLICATE_MODULE,
                    severity=SEVERITY_CRITICAL,
                    message=f"Duplicate module_id '{m.module_id}'.",
                    affected_modules=[m.module_id, seen[key]],
                    resolution_hint="Ensure every module_id is unique.",
                ))
            else:
                seen[key] = m.module_id

    def _check_overlapping(self, modules: List[ModuleDescriptor]) -> None:
        # Simple heuristic: same responsibility keywords in different modules
        by_resp: dict = defaultdict(list)
        for m in modules:
            key = (m.responsibility or m.purpose or "").strip().lower()[:80]
            if key:
                by_resp[key].append(m.module_id)
        for key, ids in by_resp.items():
            if len(ids) > 1:
                self.conflicts.append(ArchitectureConflict(
                    conflict_id=f"overlap_{ids[0]}",
                    conflict_type=CONFLICT_OVERLAPPING_RESPONSIBILITY,
                    severity=SEVERITY_HIGH,
                    message=f"Overlapping responsibility detected among {ids}.",
                    affected_modules=ids,
                    resolution_hint="Clarify and separate responsibilities.",
                ))

    def _check_incomplete(self, modules: List[ModuleDescriptor]) -> None:
        for m in modules:
            if not m.purpose and not m.responsibility:
                self.conflicts.append(ArchitectureConflict(
                    conflict_id=f"incomplete_{m.module_id}",
                    conflict_type=CONFLICT_INCOMPLETE_MODULE,
                    severity=SEVERITY_HIGH,
                    message=f"Module '{m.name}' has no purpose or responsibility.",
                    affected_modules=[m.module_id],
                    resolution_hint="Fill purpose and responsibility fields.",
                ))

    def _check_missing_interfaces(self, modules: List[ModuleDescriptor]) -> None:
        for m in modules:
            if m.category in ("core", "business", "infrastructure") and not m.interfaces:
                self.conflicts.append(ArchitectureConflict(
                    conflict_id=f"no_iface_{m.module_id}",
                    conflict_type=CONFLICT_MISSING_INTERFACE,
                    severity=SEVERITY_MEDIUM,
                    message=f"Module '{m.name}' exposes no public interface.",
                    affected_modules=[m.module_id],
                    resolution_hint="Define at least one interface for the module.",
                ))


__all__ = ["ArchitectureValidator"]
