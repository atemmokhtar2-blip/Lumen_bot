"""
Consistency validator \u2014 validates that the normalized model is
consistent.

The :class:`ConsistencyValidator` is the helper that checks the
normalized requirements for consistency.  It verifies that:

1. There are no remaining duplicates.
2. There are no conflicts between requirements.
3. There are no terminology variations for the same thing (after
   normalization).
4. No requirements were lost during normalization.

The validator does **not** fix issues \u2014 it only detects them and
records :class:`NormalizationFinding` objects and
:class:`ConflictRecord` objects.

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .report_data import (
    ConflictRecord,
    NormalizationFinding,
    NormalizedRequirement,
    TerminologyMapping,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SOURCE_REQUIREMENT_INTELLIGENCE,
)


class ConsistencyValidator:
    """Validates the consistency of the normalized requirements.

    The validator checks for remaining duplicates, conflicts,
    terminology variations, and lost requirements.  It does not fix
    issues \u2014 it only detects and records them.
    """

    def __init__(self, similarity_threshold: float = 0.85) -> None:
        self._similarity_threshold = similarity_threshold

    def validate(
        self,
        requirements: List[NormalizedRequirement],
        terminology_mappings: List[TerminologyMapping],
        original_count: int,
    ) -> Tuple[List[NormalizationFinding], List[ConflictRecord], bool]:
        """Validate the consistency of the normalized requirements.

        Parameters:
            requirements: The list of normalized requirements.
            terminology_mappings: The list of terminology
                mappings.
            original_count: The number of original requirements
                before normalization (for the lost-requirement
                check).

        Returns:
            A tuple ``(findings, conflicts, passed)`` where
            ``findings`` is a list of
            :class:`NormalizationFinding` objects, ``conflicts`` is
            a list of :class:`ConflictRecord` objects, and
            ``passed`` is ``True`` if no error-level findings were
            produced.
        """
        findings: List[NormalizationFinding] = []
        conflicts: List[ConflictRecord] = []

        # Check 1: no remaining duplicates.
        duplicate_findings = self._check_duplicates(requirements)
        findings.extend(duplicate_findings)

        # Check 2: no conflicts.
        conflict_records, conflict_findings = self._check_conflicts(
            requirements,
        )
        conflicts.extend(conflict_records)
        findings.extend(conflict_findings)

        # Check 3: no terminology variations for the same thing.
        term_findings = self._check_terminology(
            requirements, terminology_mappings,
        )
        findings.extend(term_findings)

        # Check 4: no lost requirements.
        lost_findings = self._check_lost_requirements(
            requirements, original_count,
        )
        findings.extend(lost_findings)

        # Determine if the validation passed (no error-level findings).
        has_errors = any(
            f.severity == SEVERITY_ERROR for f in findings
        )
        passed = not has_errors

        return findings, conflicts, passed

    # ----------------------------------------------------------------- #
    # Check 1: duplicates
    # ----------------------------------------------------------------- #

    def _check_duplicates(
        self,
        requirements: List[NormalizedRequirement],
    ) -> List[NormalizationFinding]:
        """Check for remaining duplicates after normalization."""
        findings: List[NormalizationFinding] = []
        seen: dict = {}

        for req in requirements:
            if req.status != "active":
                continue
            # Check by normalized name.
            key = req.name.lower().strip()
            if key and key in seen:
                findings.append(NormalizationFinding(
                    severity=SEVERITY_WARNING,
                    code="remaining_duplicate",
                    message=(
                        f"Two active requirements have the same "
                        f"normalized name '{req.name}': "
                        f"'{seen[key]}' and '{req.id}'."
                    ),
                    affected=req.name,
                    resolution_hint=(
                        "Remove the duplicate requirement or merge "
                        "it into the first one."
                    ),
                    category="consistency",
                ))
            else:
                seen[key] = req.id

        return findings

    # ----------------------------------------------------------------- #
    # Check 2: conflicts
    # ----------------------------------------------------------------- #

    def _check_conflicts(
        self,
        requirements: List[NormalizedRequirement],
    ) -> Tuple[List[ConflictRecord], List[NormalizationFinding]]:
        """Detect conflicts between requirements.

        A conflict occurs when two requirements specify contradictory
        expectations for the same aspect (e.g. one says "use SQLite"
        and another says "use PostgreSQL").
        """
        conflicts: List[ConflictRecord] = []
        findings: List[NormalizationFinding] = []

        # Build a map of aspect \u2192 values.
        # We look for "use X" patterns in descriptions.
        aspect_map: dict = {}
        for req in requirements:
            if req.status != "active":
                continue
            pairs = self._extract_use_pairs(req.description)
            for aspect, value in pairs:
                if aspect not in aspect_map:
                    aspect_map[aspect] = []
                aspect_map[aspect].append((value, req.id))

        # Check for conflicting values for the same aspect.
        conflict_id_counter = 0
        for aspect, entries in aspect_map.items():
            values = set(v.lower() for v, _ in entries)
            if len(values) > 1:
                # Find the two requirements that conflict.
                req_a_id = entries[0][1]
                req_b_id = entries[1][1]
                conflict_id_counter += 1
                conflict = ConflictRecord(
                    conflict_id=f"CONF-{conflict_id_counter:03d}",
                    requirement_a_id=req_a_id,
                    requirement_b_id=req_b_id,
                    description=(
                        f"Conflict on aspect '{aspect}': "
                        f"requirements specify different values "
                        f"({', '.join(values)})."
                    ),
                    resolution="unresolved",
                    source_artefact=SOURCE_REQUIREMENT_INTELLIGENCE,
                )
                conflicts.append(conflict)
                findings.append(NormalizationFinding(
                    severity=SEVERITY_WARNING,
                    code="conflict_detected",
                    message=(
                        f"Conflict detected on aspect '{aspect}': "
                        f"requirements specify different values "
                        f"({', '.join(values)})."
                    ),
                    affected=aspect,
                    resolution_hint=(
                        "Resolve the conflict by choosing one value "
                        "or clarifying the requirement."
                    ),
                    category="consistency",
                ))

        return conflicts, findings

    @staticmethod
    def _extract_use_pairs(description: str) -> List[tuple]:
        """Extract (aspect, value) pairs from a description.

        Looks for patterns like "use SQLite", "use PostgreSQL",
        "database: sqlite", etc.
        """
        if not description:
            return []
        pairs: List[tuple] = []
        # Match "use <word>" patterns.
        for match in re.finditer(
            r"\buse\s+(\w+)", description, re.IGNORECASE,
        ):
            value = match.group(1)
            # Heuristic: if the value is a known technology, the
            # aspect is the technology category.
            pairs.append(("technology", value))
        # Match "<aspect>: <value>" patterns.
        for match in re.finditer(
            r"\b(\w+)\s*:\s*(\w+)", description,
        ):
            aspect = match.group(1).lower()
            value = match.group(2)
            pairs.append((aspect, value))
        return pairs

    # ----------------------------------------------------------------- #
    # Check 3: terminology variations
    # ----------------------------------------------------------------- #

    def _check_terminology(
        self,
        requirements: List[NormalizedRequirement],
        terminology_mappings: List[TerminologyMapping],
    ) -> List[NormalizationFinding]:
        """Check that there are no remaining terminology variations.

        After normalization, every original term should map to a
        single canonical term.  If a term appears in multiple
        canonical forms, that is a terminology variation.
        """
        findings: List[NormalizationFinding] = []

        # Build a map of original_term \u2192 set of canonical terms.
        term_map: dict = {}
        for tm in terminology_mappings:
            key = tm.original_term.lower().strip()
            if key not in term_map:
                term_map[key] = set()
            term_map[key].add(tm.canonical_term)

        for original, canonicals in term_map.items():
            if len(canonicals) > 1:
                findings.append(NormalizationFinding(
                    severity=SEVERITY_WARNING,
                    code="terminology_variation",
                    message=(
                        f"The term '{original}' maps to multiple "
                        f"canonical terms: "
                        f"{', '.join(sorted(canonicals))}."
                    ),
                    affected=original,
                    resolution_hint=(
                        "Choose a single canonical term for this "
                        "original term."
                    ),
                    category="consistency",
                ))

        return findings

    # ----------------------------------------------------------------- #
    # Check 4: lost requirements
    # ----------------------------------------------------------------- #

    def _check_lost_requirements(
        self,
        requirements: List[NormalizedRequirement],
        original_count: int,
    ) -> List[NormalizationFinding]:
        """Check that no requirements were lost during normalization.

        The number of active + merged + deprecated requirements
        should equal the original count.  If it is less, some
        requirements were lost.
        """
        findings: List[NormalizationFinding] = []
        total = len(requirements)
        if original_count > 0 and total < original_count:
            findings.append(NormalizationFinding(
                severity=SEVERITY_ERROR,
                code="lost_requirements",
                message=(
                    f"{original_count - total} requirement(s) "
                    f"were lost during normalization. Original: "
                    f"{original_count}, after normalization: "
                    f"{total}."
                ),
                affected="requirements",
                resolution_hint=(
                    "Ensure all requirements are preserved during "
                    "normalization. Duplicates should be merged, "
                    "not removed."
                ),
                category="consistency",
            ))
        return findings


__all__ = ["ConsistencyValidator"]
