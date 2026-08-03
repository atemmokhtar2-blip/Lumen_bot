"""ArchitectureValidator — Specification 023"""

from __future__ import annotations

import logging
from typing import List

from .report_data import (
    InterfaceDescriptor,
    InterfaceContract,
    InterfaceConflict,
    CONFLICT_DUPLICATE_INTERFACE,
    CONFLICT_DUPLICATE_CONTRACT,
    CONFLICT_MISSING_CONTRACT,
    CONFLICT_STRONG_COUPLING,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
)

_log = logging.getLogger("engine.interface_contract_planning.architecture_validator")


class ArchitectureValidator:
    def validate(
        self,
        interfaces: List[InterfaceDescriptor],
        contracts: List[InterfaceContract],
    ) -> List[InterfaceConflict]:
        conflicts: List[InterfaceConflict] = []
        seen_i, seen_c = {}, {}

        for i in interfaces:
            k = i.interface_id.lower()
            if k in seen_i:
                conflicts.append(InterfaceConflict(
                    conflict_id=f"dup_iface_{i.interface_id}",
                    conflict_type=CONFLICT_DUPLICATE_INTERFACE,
                    severity=SEVERITY_CRITICAL,
                    message=f"Duplicate interface_id '{i.interface_id}'.",
                    affected_ids=[i.interface_id, seen_i[k]],
                    resolution_hint="Ensure every interface_id is unique.",
                ))
            else:
                seen_i[k] = i.interface_id

        for c in contracts:
            k = c.contract_id.lower()
            if k in seen_c:
                conflicts.append(InterfaceConflict(
                    conflict_id=f"dup_contract_{c.contract_id}",
                    conflict_type=CONFLICT_DUPLICATE_CONTRACT,
                    severity=SEVERITY_CRITICAL,
                    message=f"Duplicate contract_id '{c.contract_id}'.",
                    affected_ids=[c.contract_id, seen_c[k]],
                    resolution_hint="Ensure every contract_id is unique.",
                ))
            else:
                seen_c[k] = c.contract_id

        contract_ids = {c.contract_id for c in contracts}
        for i in interfaces:
            if i.contract_id and i.contract_id not in contract_ids:
                conflicts.append(InterfaceConflict(
                    conflict_id=f"missing_contract_{i.interface_id}",
                    conflict_type=CONFLICT_MISSING_CONTRACT,
                    severity=SEVERITY_HIGH,
                    message=f"Interface '{i.interface_id}' references missing contract '{i.contract_id}'.",
                    affected_ids=[i.interface_id, i.contract_id],
                    resolution_hint="Create the missing contract or clear the reference.",
                ))

        # Strong coupling heuristic: interface with many consumers and no version
        for i in interfaces:
            if len(i.consumer_ids) > 5 and i.version == "1.0":
                conflicts.append(InterfaceConflict(
                    conflict_id=f"coupling_{i.interface_id}",
                    conflict_type=CONFLICT_STRONG_COUPLING,
                    severity=SEVERITY_MEDIUM,
                    message=f"Interface '{i.name}' has {len(i.consumer_ids)} consumers; consider versioning.",
                    affected_ids=[i.interface_id],
                    resolution_hint="Introduce explicit versioning and stability guarantees.",
                ))

        _log.info("ArchitectureValidator found %d conflicts", len(conflicts))
        return conflicts


__all__ = ["ArchitectureValidator"]
