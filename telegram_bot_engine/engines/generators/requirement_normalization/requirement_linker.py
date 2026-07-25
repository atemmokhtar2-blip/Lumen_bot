"""
Requirement linker \u2014 links each requirement to its Feature,
Component, Priority, Dependencies, and Expected Output.

The :class:`RequirementLinker` is the helper that links each
normalized requirement to:

1. **Feature** \u2014 the feature the requirement belongs to (from
   the project context or the semantic understanding).
2. **Component** \u2014 the component the requirement belongs to
   (from the project context).
3. **Priority** \u2014 the priority of the requirement (from the
   requirement intelligence report, or inferred from the category).
4. **Dependencies** \u2014 the requirements this requirement depends
   on.
5. **Expected Output** \u2014 the expected output of the requirement
   (inferred from the description and goal).

The linker also updates the :class:`NormalizedRequirement` objects
in place (setting the ``feature``, ``component``, ``priority``,
``dependencies``, and ``expected_output`` fields).

This module is a pure processing component: it has no side effects
and does not modify the generation context.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .context_reader import ContextData
from .knowledge_reader import KnowledgeData
from .report_data import (
    LINK_KIND_COMPONENT,
    LINK_KIND_DEPENDENCY,
    LINK_KIND_EXPECTED_OUTPUT,
    LINK_KIND_FEATURE,
    NormalizedRequirement,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    RequirementLink,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_SEMANTIC_UNDERSTANDING,
)
from .requirement_intelligence_reader import (
    RequirementIntelligenceData,
)
from .semantic_understanding_reader import SemanticUnderstandingData


# Category \u2192 default priority mapping.
_CATEGORY_PRIORITY: Dict[str, str] = {
    "security": PRIORITY_CRITICAL,
    "performance": PRIORITY_HIGH,
    "functional": PRIORITY_HIGH,
    "interface": PRIORITY_HIGH,
    "deployment": PRIORITY_MEDIUM,
    "technical": PRIORITY_MEDIUM,
    "non_functional": PRIORITY_MEDIUM,
    "constraint": PRIORITY_MEDIUM,
    "usability": PRIORITY_LOW,
}


class RequirementLinker:
    """Links each normalized requirement to its Feature, Component,
    Priority, Dependencies, and Expected Output.

    The linker reads the project context (for feature and component
    names), the requirement intelligence report (for priorities and
    dependencies), and the semantic understanding report (for
    features and constraints).  It produces a list of
    :class:`RequirementLink` objects and updates the
    :class:`NormalizedRequirement` objects in place.
    """

    def link(
        self,
        requirements: List[NormalizedRequirement],
        context_data: ContextData,
        requirement_data: RequirementIntelligenceData,
        semantic_data: SemanticUnderstandingData,
        knowledge_data: KnowledgeData,
    ) -> List[RequirementLink]:
        """Link each requirement and return the links.

        Parameters:
            requirements: The list of normalized requirements.
            context_data: The project context data.
            requirement_data: The requirement intelligence data.
            semantic_data: The semantic understanding data.
            knowledge_data: The knowledge base data.

        Returns:
            A list of :class:`RequirementLink` objects.
        """
        links: List[RequirementLink] = []

        # Build feature name lookup from all sources.
        feature_names = self._collect_feature_names(
            context_data, semantic_data,
        )
        component_names = self._collect_component_names(
            context_data,
        )

        # Build a map of original_id \u2192 normalized requirement.
        # (for dependency resolution)
        original_id_map: Dict[str, NormalizedRequirement] = {}
        for req in requirements:
            if req.original_id:
                original_id_map[req.original_id] = req
            original_id_map[req.id] = req

        for req in requirements:
            # Link 1: Feature.
            feature = self._find_feature(req, feature_names)
            if feature:
                req.feature = feature
                links.append(RequirementLink(
                    requirement_id=req.id,
                    kind=LINK_KIND_FEATURE,
                    target=feature,
                    description=(
                        f"Requirement '{req.name}' belongs to "
                        f"feature '{feature}'."
                    ),
                    source_artefact=SOURCE_PROJECT_CONTEXT,
                ))

            # Link 2: Component.
            component = self._find_component(req, component_names)
            if component:
                req.component = component
                links.append(RequirementLink(
                    requirement_id=req.id,
                    kind=LINK_KIND_COMPONENT,
                    target=component,
                    description=(
                        f"Requirement '{req.name}' belongs to "
                        f"component '{component}'."
                    ),
                    source_artefact=SOURCE_PROJECT_CONTEXT,
                ))

            # Link 3: Priority.
            priority = self._determine_priority(
                req, requirement_data,
            )
            req.priority = priority

            # Link 4: Dependencies.
            deps = self._resolve_dependencies(
                req, original_id_map, requirement_data,
            )
            if deps:
                req.dependencies = deps
                for dep in deps:
                    links.append(RequirementLink(
                        requirement_id=req.id,
                        kind=LINK_KIND_DEPENDENCY,
                        target=dep,
                        description=(
                            f"Requirement '{req.name}' depends on "
                            f"'{dep}'."
                        ),
                        source_artefact=SOURCE_REQUIREMENT_INTELLIGENCE,
                    ))

            # Link 5: Expected Output.
            expected_output = self._determine_expected_output(req)
            if expected_output:
                req.expected_output = expected_output
                links.append(RequirementLink(
                    requirement_id=req.id,
                    kind=LINK_KIND_EXPECTED_OUTPUT,
                    target=expected_output,
                    description=(
                        f"Requirement '{req.name}' expects "
                        f"'{expected_output}'."
                    ),
                    source_artefact=SOURCE_REQUIREMENT_INTELLIGENCE,
                ))

        return links

    # ----------------------------------------------------------------- #
    # Feature / component collection
    # ----------------------------------------------------------------- #

    @staticmethod
    def _collect_feature_names(
        context_data: ContextData,
        semantic_data: SemanticUnderstandingData,
    ) -> List[str]:
        """Collect all feature names from the available sources."""
        names: List[str] = []
        for name in context_data.feature_names:
            if name and name not in names:
                names.append(name)
        for feature in semantic_data.intent_features:
            if feature and feature not in names:
                names.append(feature)
        return names

    @staticmethod
    def _collect_component_names(
        context_data: ContextData,
    ) -> List[str]:
        """Collect all component names from the project context."""
        names: List[str] = []
        for name in context_data.component_names:
            if name and name not in names:
                names.append(name)
        for name in context_data.dependency_names:
            if name and name not in names:
                names.append(name)
        return names

    # ----------------------------------------------------------------- #
    # Feature / component matching
    # ----------------------------------------------------------------- #

    def _find_feature(
        self,
        req: NormalizedRequirement,
        feature_names: List[str],
    ) -> str:
        """Find the feature that the requirement belongs to."""
        if not feature_names:
            return ""

        # Check if the requirement name matches a feature name.
        req_name_lower = req.name.lower()
        for name in feature_names:
            if name.lower() == req_name_lower:
                return name

        # Check if the requirement name contains a feature name.
        for name in feature_names:
            name_lower = name.lower()
            if name_lower in req_name_lower:
                return name
            if req_name_lower in name_lower:
                return name

        # Check if the description contains a feature name.
        req_desc_lower = (req.description or "").lower()
        for name in feature_names:
            name_lower = name.lower()
            if name_lower in req_desc_lower:
                return name

        return ""

    def _find_component(
        self,
        req: NormalizedRequirement,
        component_names: List[str],
    ) -> str:
        """Find the component that the requirement belongs to."""
        if not component_names:
            return ""

        # Check if the requirement name matches a component name.
        req_name_lower = req.name.lower()
        for name in component_names:
            if name.lower() == req_name_lower:
                return name

        # Check if the description contains a component name.
        req_desc_lower = (req.description or "").lower()
        for name in component_names:
            name_lower = name.lower()
            if name_lower in req_desc_lower:
                return name

        return ""

    # ----------------------------------------------------------------- #
    # Priority
    # ----------------------------------------------------------------- #

    def _determine_priority(
        self,
        req: NormalizedRequirement,
        requirement_data: RequirementIntelligenceData,
    ) -> str:
        """Determine the priority of the requirement."""
        # If the requirement already has a priority from the
        # requirement intelligence report, use it.
        if req.priority and req.priority in (
            PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM,
            PRIORITY_LOW,
        ):
            return req.priority

        # Try to find the original requirement by ID.
        for raw in requirement_data.requirements:
            if raw.id == req.original_id or raw.name == req.name:
                if raw.priority and raw.priority.lower() in (
                    "critical", "high", "medium", "low",
                ):
                    return raw.priority.lower()

        # Infer from the category.
        return _CATEGORY_PRIORITY.get(req.category, PRIORITY_MEDIUM)

    # ----------------------------------------------------------------- #
    # Dependencies
    # ----------------------------------------------------------------- #

    def _resolve_dependencies(
        self,
        req: NormalizedRequirement,
        original_id_map: Dict[str, NormalizedRequirement],
        requirement_data: RequirementIntelligenceData,
    ) -> List[str]:
        """Resolve the dependencies of the requirement."""
        deps: List[str] = []

        # Check if the requirement already has dependencies.
        if req.dependencies:
            for dep in req.dependencies:
                # Resolve the dependency ID.
                resolved = original_id_map.get(dep)
                if resolved:
                    deps.append(resolved.id)
                else:
                    deps.append(dep)

        # Try to find dependencies from the original requirement.
        for raw in requirement_data.requirements:
            if raw.id == req.original_id or raw.name == req.name:
                # The requirement intelligence report may have
                # dependencies in the reason or goal.
                deps_from_text = self._extract_dependencies_from_text(
                    raw.reason or raw.goal or raw.description,
                )
                for dep_text in deps_from_text:
                    resolved = original_id_map.get(dep_text)
                    if resolved and resolved.id not in deps:
                        deps.append(resolved.id)
                break

        return deps

    @staticmethod
    def _extract_dependencies_from_text(text: str) -> List[str]:
        """Extract dependency references from a text.

        Looks for patterns like "depends on X", "requires X".
        """
        if not text:
            return []
        deps: List[str] = []
        for match in re.finditer(
            r"\b(?:depends?\s+on|requires?)\s+(\w+)",
            text, re.IGNORECASE,
        ):
            deps.append(match.group(1))
        return deps

    # ----------------------------------------------------------------- #
    # Expected output
    # ----------------------------------------------------------------- #

    @staticmethod
    def _determine_expected_output(
        req: NormalizedRequirement,
    ) -> str:
        """Determine the expected output of the requirement.

        The expected output is inferred from the description and the
        goal of the requirement.
        """
        if not req.description:
            return ""

        # If the description already has an expected output,
        # use it.
        desc = req.description.strip()

        # Heuristic: the expected output is the first sentence of
        # the description, capitalized.
        # Find the first sentence.
        sentence_end = re.search(r"[.!?]", desc)
        if sentence_end:
            first_sentence = desc[:sentence_end.start()].strip()
        else:
            first_sentence = desc

        # Capitalize the first letter.
        if first_sentence:
            return first_sentence[0].upper() + first_sentence[1:]

        return ""


__all__ = ["RequirementLinker"]
