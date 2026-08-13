"""
Optimizer — optimizes the dependency list (Specification 009).

The :class:`DependencyOptimizer` is a stateless helper that the
:class:`DependencyResolutionEngine` calls during the *optimization*
phase.  It analyses the list of :class:`DependencyEntry` objects and
produces optimization findings and notes:

1. **Minimize libraries.**  Flags redundant libraries that provide
   overlapping functionality and could be consolidated.
2. **Prefer official.**  Flags non-official dependencies that have an
   official alternative.
3. **Avoid abandoned.**  Flags dependencies with a stability of
   ``"abandoned"``.
4. **Avoid unstable.**  Flags dependencies with a stability of
   ``"unstable"`` or ``"beta"`` (as warnings).
5. **Prefer stable.**  Confirms that all critical dependencies are
   stable.
6. **Extensibility.**  Confirms that all dependencies are marked as
   extensible so new dependencies can be added later without redesign.

The optimizer does **not** modify the dependencies — it only records
findings and optimization notes.

Data source
-----------
The optimizer reads **only** the list of :class:`DependencyEntry`
objects.  It does **not** read the user's request.
"""

from __future__ import annotations

from typing import Dict, List, Set

from .report_data import (
    DependencyEntry,
    DEPENDENCY_PRIORITY_CORE,
    DEPENDENCY_PRIORITY_INFRASTRUCTURE,
    ResolutionFinding,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    STABILITY_ABANDONED,
    STABILITY_BETA,
    STABILITY_STABLE,
    STABILITY_UNSTABLE,
    TRUST_OFFICIAL,
)


# ---------------------------------------------------------------------------#
# Known library alternatives
# ---------------------------------------------------------------------------#
#
# Maps a non-official library to its official alternative.  The
# optimizer flags the non-official one and recommends the official one.

_OFFICIAL_ALTERNATIVES: Dict[str, str] = {
    "psycopg2-binary": "psycopg2",
}


# ---------------------------------------------------------------------------#
# Known overlapping libraries (for minimization)
# ---------------------------------------------------------------------------#
#
# Groups of libraries that provide overlapping functionality.  When
# more than one library from the same group is present, the optimizer
# flags the redundancy.

_OVERLAPPING_GROUPS: List[tuple] = [
    ("aiohttp", "httpx"),
    ("psycopg2", "psycopg2-binary"),
    ("redis", "aioredis"),
]


class DependencyOptimizer:
    """Stateless helper that optimizes the dependency list.

    The optimizer is called by the
    :class:`DependencyResolutionEngine` after the
    :class:`ConflictDetector` has run.  It analyses the dependencies
    for optimization opportunities and records findings.
    """

    def optimize(
        self,
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Optimize the dependency list and record findings.

        Parameters:
            dependencies: The list of dependency entries.

        Returns:
            A list of :class:`ResolutionFinding` objects describing all
            optimization opportunities found.
        """
        findings: List[ResolutionFinding] = []

        findings.extend(self._check_minimization(dependencies))
        findings.extend(self._check_official_preference(dependencies))
        findings.extend(self._check_abandoned(dependencies))
        findings.extend(self._check_unstable(dependencies))
        findings.extend(self._check_critical_stability(dependencies))
        findings.extend(self._check_extensibility(dependencies))

        return findings

    # -----------------------------------------------------------------#
    # Optimization checks
    # -----------------------------------------------------------------#

    @staticmethod
    def _check_minimization(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Flag redundant libraries that provide overlapping functionality."""
        findings: List[ResolutionFinding] = []
        dep_names: Set[str] = {d.name for d in dependencies}

        for group in _OVERLAPPING_GROUPS:
            present = [name for name in group if name in dep_names]
            if len(present) > 1:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_WARNING,
                    code="redundant_libraries",
                    message=(
                        f"Multiple overlapping libraries detected: "
                        f"{', '.join(present)}.  Consider "
                        f"consolidating to a single library."
                    ),
                    affected=", ".join(present),
                    resolution_hint=(
                        f"Use only one of: {', '.join(present)}."
                    ),
                    category="optimization",
                ))

        return findings

    @staticmethod
    def _check_official_preference(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Flag non-official dependencies that have an official alternative."""
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            if dep.trust != TRUST_OFFICIAL:
                official = _OFFICIAL_ALTERNATIVES.get(dep.name, "")
                if official:
                    findings.append(ResolutionFinding(
                        severity=SEVERITY_INFO,
                        code="prefer_official",
                        message=(
                            f"Dependency '{dep.name}' is not "
                            f"official.  Consider using the official "
                            f"alternative '{official}'."
                        ),
                        affected=dep.name,
                        resolution_hint=(
                            f"Replace '{dep.name}' with '{official}' "
                            f"for official support."
                        ),
                        category="optimization",
                    ))

        return findings

    @staticmethod
    def _check_abandoned(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Flag abandoned dependencies."""
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            if dep.stability == STABILITY_ABANDONED:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_ERROR,
                    code="abandoned_dependency",
                    message=(
                        f"Dependency '{dep.name}' is abandoned.  "
                        f"Abandoned dependencies should be replaced "
                        f"with maintained alternatives."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Replace '{dep.name}' with a maintained "
                        f"alternative."
                    ),
                    category="optimization",
                ))

        return findings

    @staticmethod
    def _check_unstable(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Flag unstable or beta dependencies (as warnings)."""
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            if dep.stability in (STABILITY_UNSTABLE, STABILITY_BETA):
                findings.append(ResolutionFinding(
                    severity=SEVERITY_WARNING,
                    code="unstable_dependency",
                    message=(
                        f"Dependency '{dep.name}' has stability "
                        f"'{dep.stability}'.  Unstable or beta "
                        f"dependencies may cause issues."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Consider using a stable release of "
                        f"'{dep.name}'."
                    ),
                    category="optimization",
                ))

        return findings

    @staticmethod
    def _check_critical_stability(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Confirm that all critical dependencies are stable."""
        findings: List[ResolutionFinding] = []

        critical_priorities = (
            DEPENDENCY_PRIORITY_INFRASTRUCTURE,
            DEPENDENCY_PRIORITY_CORE,
        )

        for dep in dependencies:
            if dep.priority in critical_priorities:
                if dep.stability != STABILITY_STABLE:
                    findings.append(ResolutionFinding(
                        severity=SEVERITY_WARNING,
                        code="critical_not_stable",
                        message=(
                            f"Critical dependency '{dep.name}' is "
                            f"not stable (stability: "
                            f"'{dep.stability}').  Critical "
                            f"dependencies should be stable."
                        ),
                        affected=dep.name,
                        resolution_hint=(
                            f"Use a stable release of '{dep.name}'."
                        ),
                        category="optimization",
                    ))

        return findings

    @staticmethod
    def _check_extensibility(
        dependencies: List[DependencyEntry],
    ) -> List[ResolutionFinding]:
        """Confirm that all dependencies are extensible."""
        findings: List[ResolutionFinding] = []

        for dep in dependencies:
            if not dep.extensible:
                findings.append(ResolutionFinding(
                    severity=SEVERITY_INFO,
                    code="non_extensible_dependency",
                    message=(
                        f"Dependency '{dep.name}' is not marked as "
                        f"extensible.  Future expansion may require "
                        f"redesign."
                    ),
                    affected=dep.name,
                    resolution_hint=(
                        f"Confirm that '{dep.name}' can be extended "
                        f"for future needs."
                    ),
                    category="optimization",
                ))

        return findings


__all__ = ["DependencyOptimizer"]
