"""
Structure package — Phase 0.

derive_structure_plan() builds a StructurePlan from an already-grounded
formal inference result. It does not write files and does not invent domains.
"""

from .derive import derive_structure_plan, validate_structure_plan_basic

__all__ = [
    "derive_structure_plan",
    "validate_structure_plan_basic",
]
