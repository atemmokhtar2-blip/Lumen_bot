"""DependencyValidator — Specification 025"""

from __future__ import annotations

import logging
from typing import List

from .report_data import (
    DependencyItem, ResourceItem, ResourceConflict,
    CONFLICT_DUPLICATE_DEP, CONFLICT_VERSION, CONFLICT_MISSING_RESOURCE,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.resource_dependency_planning.dependency_validator")


class DependencyValidator:
    def validate(
        self,
        deps: List[DependencyItem],
        resources: List[ResourceItem],
    ) -> List[ResourceConflict]:
        conflicts: List[ResourceConflict] = []
        seen = {}
        for d in deps:
            key = d.name.lower()
            if key in seen:
                conflicts.append(ResourceConflict(
                    conflict_id=f"dup_{d.dep_id}",
                    conflict_type=CONFLICT_DUPLICATE_DEP,
                    severity=SEVERITY_HIGH,
                    message=f"Duplicate dependency '{d.name}'.",
                    affected_ids=[d.dep_id, seen[key]],
                    resolution_hint="Keep a single entry with the tightest constraint.",
                ))
            else:
                seen[key] = d.dep_id

        # Basic version presence
        for d in deps:
            if not d.version and not d.version_constraint and not d.optional:
                conflicts.append(ResourceConflict(
                    conflict_id=f"nover_{d.dep_id}",
                    conflict_type=CONFLICT_VERSION,
                    severity=SEVERITY_MEDIUM,
                    message=f"Dependency '{d.name}' has no version constraint.",
                    affected_ids=[d.dep_id],
                    resolution_hint="Pin a minimum or exact version.",
                ))

        # Required resources must have path/key
        for r in resources:
            if r.required and not r.path_or_key:
                conflicts.append(ResourceConflict(
                    conflict_id=f"missing_res_{r.resource_id}",
                    conflict_type=CONFLICT_MISSING_RESOURCE,
                    severity=SEVERITY_CRITICAL,
                    message=f"Required resource '{r.name}' has no path or key.",
                    affected_ids=[r.resource_id],
                    resolution_hint="Specify path_or_key for every required resource.",
                ))

        _log.info("DependencyValidator found %d conflicts", len(conflicts))
        return conflicts


__all__ = ["DependencyValidator"]
