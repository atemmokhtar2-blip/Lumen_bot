"""
Execution Plan \u2014 the phased build plan (Specification 004).

The :class:`ExecutionPlan` divides the project into eight ordered
phases.  The phases are fixed by the specification and their order may
**not** be changed unless the planning engine proves that reordering is
safe.

The eight phases are::

    Phase 1 \u2014 Project setup
    Phase 2 \u2014 Create structure
    Phase 3 \u2014 Build database
    Phase 4 \u2014 Create files
    Phase 5 \u2014 Generate code
    Phase 6 \u2014 Wire components
    Phase 7 \u2014 Review
    Phase 8 \u2014 Export

Each :class:`ExecutionPhase` carries:

* the phase number and name,
* the status (pending / in_progress / completed / skipped),
* the components and features assigned to the phase,
* the engines that must run in the phase,
* whether the phase can run in parallel.

The plan is populated by the planning engine based on the dependency
graph and feature units.  It is the bridge between the abstract
dependency graph and the concrete generator engines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Phase status
# ---------------------------------------------------------------------------

class PhaseStatus(Enum):
    """The status of an execution phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Default phases
# ---------------------------------------------------------------------------

@dataclass
class PhaseDefinition:
    """Static definition of a phase (its identity and rules)."""

    number: int
    name: str
    description: str
    can_parallel: bool = True
    skippable: bool = False


# The eight fixed phases.  The order is mandated by the specification
# and must not be changed unless the planning engine proves it is safe.
DEFAULT_PHASES: List[PhaseDefinition] = [
    PhaseDefinition(
        number=1,
        name="project_setup",
        description="Initialise the project, configuration, and environment.",
        can_parallel=False,
    ),
    PhaseDefinition(
        number=2,
        name="create_structure",
        description="Create the folder and file structure of the project.",
        can_parallel=False,
    ),
    PhaseDefinition(
        number=3,
        name="build_database",
        description="Build database models, migrations, and schema.",
        can_parallel=True,
        skippable=True,
    ),
    PhaseDefinition(
        number=4,
        name="create_files",
        description="Create the source files for each component.",
        can_parallel=True,
    ),
    PhaseDefinition(
        number=5,
        name="generate_code",
        description="Generate the implementation code for each component.",
        can_parallel=True,
    ),
    PhaseDefinition(
        number=6,
        name="wire_components",
        description="Wire components together and connect dependencies.",
        can_parallel=False,
    ),
    PhaseDefinition(
        number=7,
        name="review",
        description="Review the generated project for correctness.",
        can_parallel=False,
    ),
    PhaseDefinition(
        number=8,
        name="export",
        description="Export the final, packaged project.",
        can_parallel=False,
    ),
]


# ---------------------------------------------------------------------------
# Phase (runtime instance)
# ---------------------------------------------------------------------------

@dataclass
class ExecutionPhase:
    """A single phase in the execution plan.

    Attributes:
        number: The phase number (1\u20138).
        name: The phase name (machine-friendly).
        description: What the phase does.
        status: The current :class:`PhaseStatus`.
        components: The component names assigned to this phase.
        features: The feature unit names assigned to this phase.
        engines: The engine IDs that must run in this phase.
        can_parallel: Whether the phase's tasks can run in parallel.
        skippable: Whether the phase may be skipped.
        parallel_group: The parallel group from the dependency graph
            that this phase covers (for phases 3\u20135).
        notes: Extra notes for the phase.
    """

    number: int
    name: str
    description: str = ""
    status: PhaseStatus = PhaseStatus.PENDING
    components: List[str] = field(default_factory=list)
    features: List[str] = field(default_factory=list)
    engines: List[str] = field(default_factory=list)
    can_parallel: bool = True
    skippable: bool = False
    parallel_group: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def is_pending(self) -> bool:
        return self.status == PhaseStatus.PENDING

    @property
    def is_completed(self) -> bool:
        return self.status == PhaseStatus.COMPLETED

    @property
    def is_skipped(self) -> bool:
        return self.status == PhaseStatus.SKIPPED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "components": list(self.components),
            "features": list(self.features),
            "engines": list(self.engines),
            "can_parallel": self.can_parallel,
            "skippable": self.skippable,
            "parallel_group": self.parallel_group,
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

@dataclass
class ExecutionPlan:
    """The complete, phased execution plan.

    Attributes:
        phases: The ordered list of :class:`ExecutionPhase` objects.
        parallel_design: A description of which phases can run in
            parallel and which must run sequentially.
        order_locked: ``True`` when the phase order may not be changed.
    """

    phases: List[ExecutionPhase] = field(default_factory=list)
    parallel_design: Dict[str, Any] = field(default_factory=dict)
    order_locked: bool = True

    # -- queries -----------------------------------------------------------

    def get_phase(self, name: str) -> Optional[ExecutionPhase]:
        for p in self.phases:
            if p.name == name:
                return p
        return None

    def get_phase_by_number(self, number: int) -> Optional[ExecutionPhase]:
        for p in self.phases:
            if p.number == number:
                return p
        return None

    @property
    def phase_names(self) -> List[str]:
        return [p.name for p in self.phases]

    def all_phases_have_tasks(self) -> bool:
        """Return ``True`` when every phase has at least one component
        or feature assigned (or is explicitly skippable)."""
        for p in self.phases:
            if not p.components and not p.features and not p.engines:
                if not p.skippable:
                    return False
        return True

    def phases_are_contiguous(self) -> bool:
        """Return ``True`` when phase numbers are contiguous 1\u2026N."""
        if not self.phases:
            return True
        numbers = sorted(p.number for p in self.phases)
        return numbers == list(range(1, len(numbers) + 1))

    def is_complete(self) -> bool:
        """Return ``True`` when the plan is complete and valid.

        A plan is complete when:

        * it has all eight phases,
        * every phase has at least one task (or is skippable),
        * the phase numbers are contiguous,
        * the order is locked.
        """
        if len(self.phases) != len(DEFAULT_PHASES):
            return False
        if not self.phases_are_contiguous():
            return False
        if not self.all_phases_have_tasks():
            return False
        if not self.order_locked:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phases": [p.to_dict() for p in self.phases],
            "parallel_design": dict(self.parallel_design),
            "order_locked": self.order_locked,
            "is_complete": self.is_complete(),
        }


__all__ = [
    "ExecutionPlan",
    "ExecutionPhase",
    "PhaseStatus",
    "PhaseDefinition",
    "DEFAULT_PHASES",
]
