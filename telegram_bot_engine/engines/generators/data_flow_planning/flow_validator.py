"""FlowValidator — Specification 024"""

from __future__ import annotations

import logging
from typing import List

from .report_data import (
    DataSource, DataDestination, DataFlowPath, DataFlowConflict,
    CONFLICT_MISSING_PATH, CONFLICT_INFINITE_LOOP, CONFLICT_DUPLICATE_FLOW,
    CONFLICT_ORPHAN_SOURCE, SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.data_flow_planning.flow_validator")


class FlowValidator:
    def validate(
        self,
        sources: List[DataSource],
        destinations: List[DataDestination],
        paths: List[DataFlowPath],
    ) -> List[DataFlowConflict]:
        conflicts: List[DataFlowConflict] = []
        src_ids = {s.source_id for s in sources}
        dst_ids = {d.destination_id for d in destinations}
        seen_paths = {}

        for p in paths:
            if p.source_id not in src_ids:
                conflicts.append(DataFlowConflict(
                    conflict_id=f"missing_src_{p.path_id}",
                    conflict_type=CONFLICT_MISSING_PATH,
                    severity=SEVERITY_CRITICAL,
                    message=f"Path '{p.path_id}' references unknown source '{p.source_id}'.",
                    affected_ids=[p.path_id, p.source_id],
                    resolution_hint="Define the source or fix the reference.",
                ))
            if p.destination_id not in dst_ids:
                conflicts.append(DataFlowConflict(
                    conflict_id=f"missing_dst_{p.path_id}",
                    conflict_type=CONFLICT_MISSING_PATH,
                    severity=SEVERITY_CRITICAL,
                    message=f"Path '{p.path_id}' references unknown destination '{p.destination_id}'.",
                    affected_ids=[p.path_id, p.destination_id],
                    resolution_hint="Define the destination or fix the reference.",
                ))
            # Simple loop detection: repeated step
            if len(p.steps) != len(set(p.steps)):
                conflicts.append(DataFlowConflict(
                    conflict_id=f"loop_{p.path_id}",
                    conflict_type=CONFLICT_INFINITE_LOOP,
                    severity=SEVERITY_CRITICAL,
                    message=f"Path '{p.path_id}' contains repeated steps (possible loop).",
                    affected_ids=[p.path_id],
                    resolution_hint="Remove cyclic steps from the path.",
                ))
            key = f"{p.source_id}->{p.destination_id}"
            if key in seen_paths:
                conflicts.append(DataFlowConflict(
                    conflict_id=f"dup_flow_{p.path_id}",
                    conflict_type=CONFLICT_DUPLICATE_FLOW,
                    severity=SEVERITY_MEDIUM,
                    message=f"Duplicate flow {key}.",
                    affected_ids=[p.path_id, seen_paths[key]],
                    resolution_hint="Merge or differentiate the flows.",
                ))
            else:
                seen_paths[key] = p.path_id

        used_sources = {p.source_id for p in paths}
        for s in sources:
            if s.source_id not in used_sources:
                conflicts.append(DataFlowConflict(
                    conflict_id=f"orphan_{s.source_id}",
                    conflict_type=CONFLICT_ORPHAN_SOURCE,
                    severity=SEVERITY_MEDIUM,
                    message=f"Source '{s.name}' is never consumed by any path.",
                    affected_ids=[s.source_id],
                    resolution_hint="Add a path or remove the unused source.",
                ))

        _log.info("FlowValidator found %d conflicts", len(conflicts))
        return conflicts


__all__ = ["FlowValidator"]
