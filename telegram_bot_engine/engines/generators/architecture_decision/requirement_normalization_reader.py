"""
Requirement normalization reader -- reads the Normalized Requirement
Model from the generation context.

The :class:`RequirementNormalizationReader` is responsible for
obtaining the ``requirement_normalization_report`` artefact (produced
by the
:class:`~telegram_bot_engine.engines.generators.requirement_normalization.RequirementNormalizationEngine`)
and returning a normalised :class:`RequirementNormalizationData`
object.

The reader is tolerant: it never raises when the normalized
requirement model is not available.  It returns a
:class:`RequirementNormalizationData` with ``available=False`` in that
case.

This module is a pure reader: it has no side effects and does not
modify the generation context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ....core.context import GenerationContext
from .report_data import SOURCE_NORMALIZED_REQUIREMENTS


# ---------------------------------------------------------------------------#
# Normalized requirement (lightweight view)
# ---------------------------------------------------------------------------#

@dataclass
class NormalizedRequirementView:
    """A lightweight view of a single normalized requirement.

    Attributes:
        id: The canonical ID (e.g. ``"NREQ-001"``).
        name: The canonical, machine-readable name.
        display_name: The human-readable display name.
        description: The canonical, normalized description.
        category: The unified category.
        priority: The priority.
        status: The status.
        feature: The feature this requirement belongs to.
        component: The component this requirement belongs to.
        dependencies: The list of requirement IDs this
            requirement depends on.
        expected_output: The expected output.
    """

    id: str = ""
    name: str = ""
    display_name: str = ""
    description: str = ""
    category: str = ""
    priority: str = ""
    status: str = ""
    feature: str = ""
    component: str = ""
    dependencies: List[str] = field(default_factory=list)
    expected_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "status": self.status,
            "feature": self.feature,
            "component": self.component,
            "dependencies": list(self.dependencies),
            "expected_output": self.expected_output,
        }


# ---------------------------------------------------------------------------#
# Requirement normalization data
# ---------------------------------------------------------------------------#

@dataclass
class RequirementNormalizationData:
    """Normalised view of the Normalized Requirement Model.

    This is a lightweight container that holds the information the
    Architecture Decision Engine needs from the Normalized
    Requirement Model.

    Attributes:
        requirements: The list of normalized requirements.
        canonical_names: The list of canonical name strings.
        requirement_count: The number of requirements.
        active_requirement_count: The number of active
            requirements.
        category_counts: A mapping of category -> count.
        priority_counts: A mapping of priority -> count.
        all_linked: Whether all requirements are linked.
        ready: Whether the normalized model was ready.
        confidence: The confidence score.
        available: Whether the normalized model was available.
    """

    requirements: List[NormalizedRequirementView] = field(
        default_factory=list
    )
    canonical_names: List[str] = field(default_factory=list)
    requirement_count: int = 0
    active_requirement_count: int = 0
    category_counts: Dict[str, int] = field(default_factory=dict)
    priority_counts: Dict[str, int] = field(default_factory=dict)
    all_linked: bool = False
    ready: bool = False
    confidence: float = 0.0
    available: bool = False

    @property
    def source_artefact(self) -> str:
        return SOURCE_NORMALIZED_REQUIREMENTS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirements": [r.to_dict() for r in self.requirements],
            "canonical_names": list(self.canonical_names),
            "requirement_count": self.requirement_count,
            "active_requirement_count": self.active_requirement_count,
            "category_counts": dict(self.category_counts),
            "priority_counts": dict(self.priority_counts),
            "all_linked": self.all_linked,
            "ready": self.ready,
            "confidence": self.confidence,
            "available": self.available,
        }


class RequirementNormalizationReader:
    """Reads the Normalized Requirement Model from the generation
    context.

    The reader looks for the ``requirement_normalization_report``
    artefact.  When present, it extracts the requirements, canonical
    names, category counts, priority counts, and readiness.  When
    absent, it returns a :class:`RequirementNormalizationData` with
    ``available=False``.
    """

    def read(
        self, context: GenerationContext,
    ) -> RequirementNormalizationData:
        """Read the normalized model and return a
        :class:`RequirementNormalizationData`.
        """
        report = context.get("requirement_normalization_report")
        if report is None:
            return RequirementNormalizationData(available=False)

        return self._read_from_report(report)

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _read_from_report(
        self, report: Any,
    ) -> RequirementNormalizationData:
        """Extract data from the normalization report artefact."""
        def get_attr(name: str, default: Any = None) -> Any:
            if hasattr(report, name):
                return getattr(report, name)
            if isinstance(report, dict):
                return report.get(name, default)
            return default

        # Requirements.
        requirements_raw = get_attr("requirements", []) or []
        requirements: List[NormalizedRequirementView] = []
        if isinstance(requirements_raw, (list, tuple)):
            for req in requirements_raw:
                if isinstance(req, dict):
                    req_id = str(req.get("id", "") or "")
                    req_name = str(req.get("name", "") or "")
                    req_display = str(
                        req.get("display_name", "") or ""
                    )
                    req_desc = str(req.get("description", "") or "")
                    req_cat = str(req.get("category", "") or "")
                    req_pri = str(req.get("priority", "") or "")
                    req_status = str(req.get("status", "") or "")
                    req_feature = str(req.get("feature", "") or "")
                    req_component = str(req.get("component", "") or "")
                    req_deps = req.get("dependencies", []) or []
                    req_output = str(req.get("expected_output", "") or "")
                else:
                    req_id = str(getattr(req, "id", "") or "")
                    req_name = str(getattr(req, "name", "") or "")
                    req_display = str(
                        getattr(req, "display_name", "") or ""
                    )
                    req_desc = str(
                        getattr(req, "description", "") or ""
                    )
                    req_cat = str(getattr(req, "category", "") or "")
                    req_pri = str(getattr(req, "priority", "") or "")
                    req_status = str(getattr(req, "status", "") or "")
                    req_feature = str(getattr(req, "feature", "") or "")
                    req_component = str(getattr(req, "component", "") or "")
                    req_deps = getattr(req, "dependencies", []) or []
                    req_output = str(
                        getattr(req, "expected_output", "") or ""
                    )
                if isinstance(req_deps, (list, tuple)):
                    req_deps = [str(d) for d in req_deps]
                else:
                    req_deps = []
                requirements.append(NormalizedRequirementView(
                    id=req_id,
                    name=req_name,
                    display_name=req_display,
                    description=req_desc,
                    category=req_cat,
                    priority=req_pri,
                    status=req_status,
                    feature=req_feature,
                    component=req_component,
                    dependencies=req_deps,
                    expected_output=req_output,
                ))

        # Canonical names.
        canonical_names_raw = get_attr("canonical_names", []) or []
        canonical_names: List[str] = []
        if isinstance(canonical_names_raw, (list, tuple)):
            for cn in canonical_names_raw:
                if isinstance(cn, dict):
                    form = str(cn.get("canonical_form", "") or "")
                elif hasattr(cn, "canonical_form"):
                    form = str(getattr(cn, "canonical_form", "") or "")
                elif isinstance(cn, str):
                    form = cn
                else:
                    form = ""
                if form:
                    canonical_names.append(form)

        # Counts and metadata.
        requirement_count = int(get_attr("requirement_count", 0) or 0)
        active_requirement_count = int(
            get_attr("active_requirement_count", 0) or 0
        )

        # Category counts.
        category_counts: Dict[str, int] = {}
        if hasattr(report, "category_counts"):
            try:
                cc = report.category_counts()
                if isinstance(cc, dict):
                    category_counts = {
                        str(k): int(v) for k, v in cc.items()
                    }
            except (TypeError, ValueError):
                pass
        elif isinstance(get_attr("category_counts"), dict):
            category_counts = {
                str(k): int(v)
                for k, v in get_attr("category_counts").items()
            }

        # Priority counts.
        priority_counts: Dict[str, int] = {}
        if hasattr(report, "priority_counts"):
            try:
                pc = report.priority_counts()
                if isinstance(pc, dict):
                    priority_counts = {
                        str(k): int(v) for k, v in pc.items()
                    }
            except (TypeError, ValueError):
                pass
        elif isinstance(get_attr("priority_counts"), dict):
            priority_counts = {
                str(k): int(v)
                for k, v in get_attr("priority_counts").items()
            }

        # All linked.
        all_linked = bool(get_attr("all_linked", False))

        # Ready.
        ready = bool(get_attr("ready", False))

        # Confidence.
        confidence = float(get_attr("confidence", 0.0) or 0.0)

        return RequirementNormalizationData(
            requirements=requirements,
            canonical_names=canonical_names,
            requirement_count=requirement_count,
            active_requirement_count=active_requirement_count,
            category_counts=category_counts,
            priority_counts=priority_counts,
            all_linked=all_linked,
            ready=ready,
            confidence=confidence,
            available=True,
        )


__all__ = [
    "RequirementNormalizationReader",
    "RequirementNormalizationData",
    "NormalizedRequirementView",
]
