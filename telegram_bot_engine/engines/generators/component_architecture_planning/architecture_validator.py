"""ArchitectureValidator — Specification 022"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import List

from .report_data import (
    ComponentDescriptor,
    ComponentConflict,
    CONFLICT_DUPLICATE_COMPONENT,
    CONFLICT_OVERLAPPING_RESPONSIBILITY,
    CONFLICT_MISSING_INTERFACE,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.component_architecture_planning.architecture_validator")


class ArchitectureValidator:
    def validate(self, components: List[ComponentDescriptor]) -> List[ComponentConflict]:
        conflicts: List[ComponentConflict] = []
        seen = {}
        for c in components:
            key = c.component_id.lower()
            if key in seen:
                conflicts.append(ComponentConflict(
                    conflict_id=f"dup_{c.component_id}",
                    conflict_type=CONFLICT_DUPLICATE_COMPONENT,
                    severity=SEVERITY_CRITICAL,
                    message=f"Duplicate component_id '{c.component_id}'.",
                    affected_components=[c.component_id, seen[key]],
                    resolution_hint="Ensure every component_id is unique.",
                ))
            else:
                seen[key] = c.component_id

        by_resp: dict = defaultdict(list)
        for c in components:
            r = (c.responsibility or c.purpose or "").strip().lower()[:80]
            if r:
                by_resp[r].append(c.component_id)
        for r, ids in by_resp.items():
            if len(ids) > 1:
                conflicts.append(ComponentConflict(
                    conflict_id=f"overlap_{ids[0]}",
                    conflict_type=CONFLICT_OVERLAPPING_RESPONSIBILITY,
                    severity=SEVERITY_HIGH,
                    message=f"Overlapping responsibility among {ids}.",
                    affected_components=ids,
                    resolution_hint="Separate responsibilities clearly.",
                ))

        for c in components:
            if c.kind in ("service", "controller", "repository", "adapter") and not c.interfaces:
                conflicts.append(ComponentConflict(
                    conflict_id=f"no_iface_{c.component_id}",
                    conflict_type=CONFLICT_MISSING_INTERFACE,
                    severity=SEVERITY_MEDIUM,
                    message=f"Component '{c.name}' has no public interface.",
                    affected_components=[c.component_id],
                    resolution_hint="Define at least one interface.",
                ))

        _log.info("ArchitectureValidator found %d conflicts", len(conflicts))
        return conflicts


__all__ = ["ArchitectureValidator"]
