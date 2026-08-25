"""
Quality Scorer (Specification 005).

The :class:`QualityScorer` computes a quality breakdown for a
:class:`ProjectBlueprint`.  It produces a :class:`QualityScore` with four
sub-scores and an overall weighted average.

Scoring philosophy
------------------
Each sub-score starts at 1.0 (perfect) and is reduced by detected
problems.  The reduction is proportional to the severity of the issue
and the fraction of the blueprint affected.  The scorer never raises —
it always returns a numeric score.

Sub-scores
----------
* **structure_quality** — based on the completeness of the project
  identity, the presence of a structure root, and the number of
  structure entries.
* **dependency_quality** — based on the health of the dependency graph:
  no cycles, no dangling dependencies, and a reasonable number of
  connected nodes.
* **feature_quality** — based on how well features are described: each
  feature has a description, a phase, and no duplicates.
* **planning_quality** — based on the completeness of the execution
  plan: all phases present, contiguous, and each phase has tasks.

Overall score
-------------
The overall score is a weighted average of the four sub-scores.  The
weights are configurable via the engine configuration; the defaults are:

* structure_quality: 0.25
* dependency_quality: 0.30
* feature_quality: 0.20
* planning_quality: 0.25
"""

from __future__ import annotations

from typing import Any, Dict

from .validation_report import QualityScore
from ..project_planner.blueprint import ProjectBlueprint
from ..project_planner.feature_unit import FeatureUnit
from ..project_planner.dependency_graph import DependencyGraph
from ..project_planner.execution_plan import ExecutionPlan


# Default weights for the overall score.  They sum to 1.0.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "structure_quality": 0.25,
    "dependency_quality": 0.30,
    "feature_quality": 0.20,
    "planning_quality": 0.25,
}

# Default minimum required score for approval.
DEFAULT_MINIMUM_REQUIRED: float = 0.7


class QualityScorer:
    """Computes the quality breakdown of a :class:`ProjectBlueprint`.

    The scorer is stateless; it receives the blueprint (and optionally
    the layer results / conflict counts) and returns a
    :class:`QualityScore`.
    """

    def __init__(
        self,
        weights: Dict[str, float] | None = None,
        minimum_required: float = DEFAULT_MINIMUM_REQUIRED,
    ) -> None:
        self._weights = dict(weights) if weights else dict(DEFAULT_WEIGHTS)
        # Normalise weights so they sum to 1.0.
        total = sum(self._weights.values())
        if total > 0:
            self._weights = {k: v / total for k, v in self._weights.items()}
        self._minimum_required = minimum_required

    def score(
        self,
        blueprint: ProjectBlueprint,
        error_count: int = 0,
        warning_count: int = 0,
    ) -> QualityScore:
        """Compute and return the :class:`QualityScore` for *blueprint*."""
        structure = self._score_structure(blueprint)
        dependency = self._score_dependency(blueprint)
        feature = self._score_features(blueprint)
        planning = self._score_planning(blueprint)

        # Weighted average.
        overall = (
            self._weights.get("structure_quality", 0.0) * structure
            + self._weights.get("dependency_quality", 0.0) * dependency
            + self._weights.get("feature_quality", 0.0) * feature
            + self._weights.get("planning_quality", 0.0) * planning
        )

        # Apply a penalty for errors.  Each error reduces the overall
        # score, but the score is clamped to [0.0, 1.0].
        if error_count > 0:
            penalty = min(0.3, 0.05 * error_count)
            overall = max(0.0, overall - penalty)

        # Warnings have a smaller penalty.
        if warning_count > 0:
            penalty = min(0.1, 0.01 * warning_count)
            overall = max(0.0, overall - penalty)

        overall = max(0.0, min(1.0, overall))
        meets = overall >= self._minimum_required

        return QualityScore(
            structure_quality=structure,
            dependency_quality=dependency,
            feature_quality=feature,
            planning_quality=planning,
            overall=overall,
            minimum_required=self._minimum_required,
            meets_minimum=meets,
        )

    # -- sub-scores -------------------------------------------------------#

    def _score_structure(self, blueprint: ProjectBlueprint) -> float:
        """Score the project structure and identity completeness."""
        score = 1.0
        identity = blueprint.identity

        # Identity completeness.
        if not identity.name:
            score -= 0.3
        if not identity.bot_type:
            score -= 0.15
        if not identity.language:
            score -= 0.1
        if not identity.framework:
            score -= 0.1
        # A database is optional, so missing it is not penalised.

        # Structure entries.
        if not blueprint.structure.root:
            score -= 0.2
        if not blueprint.structure.entries:
            score -= 0.2
        elif len(blueprint.structure.entries) < 3:
            score -= 0.1  # very thin structure.

        return max(0.0, min(1.0, score))

    def _score_dependency(self, blueprint: ProjectBlueprint) -> float:
        """Score the health of the dependency graph."""
        graph: DependencyGraph = blueprint.dependency_graph
        score = 1.0

        if graph.count() == 0:
            # No nodes — a trivial plan.  Not penalised heavily.
            return 0.9

        if graph.has_cycle():
            score -= 0.5

        dangling = graph.dangling_dependencies()
        if dangling:
            # Each dangling dependency reduces the score.
            score -= min(0.3, 0.05 * len(dangling))

        # Reward connectedness: the more nodes with dependents, the
        # better the graph structure.
        nodes = graph.all_nodes()
        if nodes:
            connected = sum(1 for n in nodes if n.dependents)
            ratio = connected / len(nodes)
            # If nothing is connected to anything, reduce the score.
            if ratio < 0.2:
                score -= 0.1

        return max(0.0, min(1.0, score))

    def _score_features(self, blueprint: ProjectBlueprint) -> float:
        """Score the quality of the feature breakdown."""
        features = blueprint.features
        if not features:
            # No features — the plan is essentially empty.
            return 0.8

        score = 1.0
        total = len(features)

        # Duplicate detection.
        names = [f.name for f in features]
        duplicates = len(names) - len(set(names))
        if duplicates:
            score -= min(0.3, 0.1 * duplicates)

        # Each feature should have a description and a phase.
        no_description = sum(1 for f in features if not f.description)
        no_phase = sum(1 for f in features if not f.phase)
        if total > 0:
            score -= 0.05 * (no_description / total)
            score -= 0.05 * (no_phase / total)

        return max(0.0, min(1.0, score))

    def _score_planning(self, blueprint: ProjectBlueprint) -> float:
        """Score the completeness of the execution plan."""
        plan: ExecutionPlan = blueprint.execution_plan
        if not plan.phases:
            return 0.0

        score = 1.0

        if not plan.is_complete():
            # is_complete checks all eight phases, contiguity, and
            # that every phase has tasks (or is skippable).
            score -= 0.4

        if not plan.phases_are_contiguous():
            score -= 0.2

        # Count phases with no tasks.
        empty_phases = 0
        for phase in plan.phases:
            if (not phase.components and not phase.features
                    and not phase.engines and not phase.skippable):
                empty_phases += 1
        if plan.phases and empty_phases > 0:
            score -= min(0.2, 0.05 * empty_phases)

        return max(0.0, min(1.0, score))


__all__ = [
    "QualityScorer",
    "DEFAULT_WEIGHTS",
    "DEFAULT_MINIMUM_REQUIRED",
]
