"""
Requirement Normalization Report data model (Specification 014).

This module defines the :class:`NormalizationReport` — the complete,
authoritative output of the
:class:`~telegram_bot_engine.engines.generators.requirement_normalization.RequirementNormalizationEngine`.

The Requirement Normalization Engine is the engine responsible for
transforming **all** user requirements into a unified, canonical model
that all downstream engines can understand.  Its sole function is
normalization — it does not write code, create files, build the
project, or make architectural decisions.

Data sources
-------------
The engine reads **five** data sources:

1. **User Request** — the raw user message (via the
   ``analysis_report`` artefact, or the raw ``context.request``).
2. **Requirement Intelligence Report** — the
   ``requirement_intelligence_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.requirement_intelligence.RequirementIntelligenceEngine`.
3. **Semantic Understanding Report** — the
   ``semantic_understanding_report`` artefact produced by the
   :class:`~telegram_bot_engine.engines.generators.semantic_understanding.SemanticUnderstandingEngine`.
4. **Project Context** — the ``project_context`` artefact produced by
   the
   :class:`~telegram_bot_engine.engines.generators.project_context.ProjectContextEngine`.
5. **Knowledge Base** — the ``knowledge_base`` artefact, if present
   (a free-form dictionary of pre-approved assumptions, synonyms,
   abbreviations, and domain knowledge).

Design principles
-----------------
* **Unification, not interpretation.**  The engine does not interpret
  or add new meaning to requirements.  It converts all the different
  forms, names, and terms the user used into a single, canonical
  model.
* **No duplicates.**  The engine removes duplicate requirements and
  irrelevant information.
* **No loss.**  The engine preserves all important information.  No
  requirement is lost during normalization.
* **Consistency.**  The engine validates that there are no
  duplicates, no conflicts, and no terminology variations for the
  same thing.
* **Linking.**  Each requirement is linked to its Feature,
  Component, Priority, Dependencies, and Expected Output.
* **Caching.**  The engine caches the normalized model so that it
  does not re-normalize when the requirements have not changed.
* **Scalability.**  The engine is designed to handle small, medium,
  large, and very large projects with hundreds of requirements.
* **Quality gate.**  No requirement passes unless it has been
  converted to the canonical model.
* **Traceability.**  Every normalization records the data source it
  was derived from (``source_artefact``) so any downstream decision
  can trace its data back to the original source.

The report is a plain data container — no logic lives here.  The
engine and its helpers populate it; downstream consumers read it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------#
# Source-artefact constants
# ---------------------------------------------------------------------------#
#
# Every normalization records the data source it was derived from.
# These constants are the stable identifiers for the five data
# sources.

SOURCE_USER_REQUEST = "user_request"
SOURCE_REQUIREMENT_INTELLIGENCE = "requirement_intelligence"
SOURCE_SEMANTIC_UNDERSTANDING = "semantic_understanding"
SOURCE_PROJECT_CONTEXT = "project_context"
SOURCE_KNOWLEDGE_BASE = "knowledge_base"

ALL_SOURCES = (
    SOURCE_USER_REQUEST,
    SOURCE_REQUIREMENT_INTELLIGENCE,
    SOURCE_SEMANTIC_UNDERSTANDING,
    SOURCE_PROJECT_CONTEXT,
    SOURCE_KNOWLEDGE_BASE,
)


# ---------------------------------------------------------------------------#
# Severity constants
# ---------------------------------------------------------------------------#

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

ALL_SEVERITIES = (SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO)


# ---------------------------------------------------------------------------#
# Requirement status constants
# ---------------------------------------------------------------------------#
#
# The status of a normalized requirement.

STATUS_ACTIVE = "active"
STATUS_DEPRECATED = "deprecated"
STATUS_MERGED = "merged"
STATUS_REMOVED = "removed"

ALL_STATUSES = (STATUS_ACTIVE, STATUS_DEPRECATED, STATUS_MERGED,
                STATUS_REMOVED)


# ---------------------------------------------------------------------------#
# Requirement priority constants
# ---------------------------------------------------------------------------#

PRIORITY_CRITICAL = "critical"
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

ALL_PRIORITIES = (PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM,
                  PRIORITY_LOW)

# Priority weight mapping for sorting.
PRIORITY_WEIGHTS: Dict[str, int] = {
    PRIORITY_CRITICAL: 4,
    PRIORITY_HIGH: 3,
    PRIORITY_MEDIUM: 2,
    PRIORITY_LOW: 1,
}


# ---------------------------------------------------------------------------#
# Requirement category constants
# ---------------------------------------------------------------------------#

CATEGORY_FUNCTIONAL = "functional"
CATEGORY_NON_FUNCTIONAL = "non_functional"
CATEGORY_TECHNICAL = "technical"
CATEGORY_CONSTRAINT = "constraint"
CATEGORY_INTERFACE = "interface"
CATEGORY_SECURITY = "security"
CATEGORY_PERFORMANCE = "performance"
CATEGORY_USABILITY = "usability"
CATEGORY_DEPLOYMENT = "deployment"

ALL_CATEGORIES = (
    CATEGORY_FUNCTIONAL,
    CATEGORY_NON_FUNCTIONAL,
    CATEGORY_TECHNICAL,
    CATEGORY_CONSTRAINT,
    CATEGORY_INTERFACE,
    CATEGORY_SECURITY,
    CATEGORY_PERFORMANCE,
    CATEGORY_USABILITY,
    CATEGORY_DEPLOYMENT,
)


# ---------------------------------------------------------------------------#
# Link kind constants
# ---------------------------------------------------------------------------#
#
# The kind of link between a requirement and a feature/component.

LINK_KIND_FEATURE = "feature"
LINK_KIND_COMPONENT = "component"
LINK_KIND_DEPENDENCY = "dependency"
LINK_KIND_EXPECTED_OUTPUT = "expected_output"

ALL_LINK_KINDS = (LINK_KIND_FEATURE, LINK_KIND_COMPONENT,
                  LINK_KIND_DEPENDENCY, LINK_KIND_EXPECTED_OUTPUT)


# ---------------------------------------------------------------------------#
# Cache status constants
# ---------------------------------------------------------------------------#

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_STALE = "stale"
CACHE_DISABLED = "disabled"

ALL_CACHE_STATUSES = (CACHE_HIT, CACHE_MISS, CACHE_STALE, CACHE_DISABLED)


# ---------------------------------------------------------------------------#
# Confidence level constants
# ---------------------------------------------------------------------------#

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

ALL_CONFIDENCE_LEVELS = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)

CONFIDENCE_HIGH_THRESHOLD = 0.8
CONFIDENCE_MEDIUM_THRESHOLD = 0.6


# ---------------------------------------------------------------------------#
# Canonical name entry
# ---------------------------------------------------------------------------#

@dataclass
class CanonicalName:
    """A canonical (unified) name for a component, feature, module, or
    term.

    The normalization engine unifies all the different names the user
    used to refer to the same thing into a single canonical name.
    This data class records the canonical name and all the variants
    that were mapped to it.

    Attributes:
        canonical_form: The canonical, unified name.
        original_forms: The list of original forms that were
            mapped to this canonical name.
        kind: The kind of name (``"component"``, ``"feature"``,
            ``"module"``, ``"term"``).
        source_artefact: The artefact this name was derived
            from.
    """

    canonical_form: str = ""
    original_forms: List[str] = field(default_factory=list)
    kind: str = "component"
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_form": self.canonical_form,
            "original_forms": list(self.original_forms),
            "kind": self.kind,
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Terminology mapping
# ---------------------------------------------------------------------------#

@dataclass
class TerminologyMapping:
    """A terminology mapping — a term the user used mapped to its
    canonical term.

    The normalization engine unifies all the different terms the user
    used to refer to the same concept into a single canonical term.
    This data class records the mapping.

    Attributes:
        original_term: The original term the user used.
        canonical_term: The canonical, unified term.
        kind: The kind of term (``"concept"``, ``"technology"``,
            ``"action"``, ``"general"``).
        source_artefact: The artefact this mapping was derived
            from.
    """

    original_term: str = ""
    canonical_term: str = ""
    kind: str = "general"
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_term": self.original_term,
            "canonical_term": self.canonical_term,
            "kind": self.kind,
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Requirement link
# ---------------------------------------------------------------------------#

@dataclass
class RequirementLink:
    """A link between a requirement and a feature, component,
    dependency, or expected output.

    The normalization engine links each requirement to its Feature,
    Component, Priority, Dependencies, and Expected Output.  This
    data class records a single link.

    Attributes:
        requirement_id: The ID of the requirement this link
            belongs to.
        kind: The kind of link (one of the ``LINK_KIND_*``
            constants).
        target: The name or ID of the linked entity (feature
            name, component name, dependency name, or expected
            output description).
        description: A human-readable description of the link.
        source_artefact: The artefact this link was derived
            from.
    """

    requirement_id: str = ""
    kind: str = LINK_KIND_FEATURE
    target: str = ""
    description: str = ""
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "kind": self.kind,
            "target": self.target,
            "description": self.description,
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Duplicate record
# ---------------------------------------------------------------------------#

@dataclass
class DuplicateRecord:
    """A record of a duplicate requirement that was removed.

    The normalization engine removes duplicate requirements.  This
    data class records each duplicate that was found and removed,
    including which requirement it was merged into.

    Attributes:
        duplicate_id: The ID of the duplicate requirement.
        duplicate_description: The description of the
            duplicate.
        merged_into_id: The ID of the requirement the
            duplicate was merged into.
        similarity: 0.0–1.0 similarity score.
        source_artefact: The artefact this duplicate was
            derived from.
    """

    duplicate_id: str = ""
    duplicate_description: str = ""
    merged_into_id: str = ""
    similarity: float = 1.0
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duplicate_id": self.duplicate_id,
            "duplicate_description": self.duplicate_description,
            "merged_into_id": self.merged_into_id,
            "similarity": self.similarity,
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Conflict record
# ---------------------------------------------------------------------------#

@dataclass
class ConflictRecord:
    """A record of a conflict between two requirements.

    The normalization engine detects conflicts between requirements
    (e.g. one requirement says "use SQLite" and another says "use
    PostgreSQL").  This data class records the conflict.

    Attributes:
        conflict_id: A unique identifier for this conflict.
        requirement_a_id: The ID of the first requirement.
        requirement_b_id: The ID of the second requirement.
        description: A human-readable description of the
            conflict.
        resolution: How the conflict was resolved (or
            ``"unresolved"`` if not resolved).
        source_artefact: The artefact this conflict was
            derived from.
    """

    conflict_id: str = ""
    requirement_a_id: str = ""
    requirement_b_id: str = ""
    description: str = ""
    resolution: str = "unresolved"
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "requirement_a_id": self.requirement_a_id,
            "requirement_b_id": self.requirement_b_id,
            "description": self.description,
            "resolution": self.resolution,
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# Normalization finding
# ---------------------------------------------------------------------------#

@dataclass
class NormalizationFinding:
    """A general finding produced during requirement normalization.

    Attributes:
        severity: ``"error"``, ``"warning"``, or ``"info"``.
        code: A short, machine-readable code (e.g.
            ``"duplicate_requirement"``).
        message: A human-readable description.
        affected: The name of the affected element.
        resolution_hint: An optional suggestion on how to fix
            the issue.
        category: The finding category (``"consistency"``,
            ``"quality"``, ``"cache"``, ``"linking"``).
    """

    severity: str = SEVERITY_WARNING
    code: str = ""
    message: str = ""
    affected: str = ""
    resolution_hint: str = ""
    category: str = "validation"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


# ---------------------------------------------------------------------------#
# Cache info
# ---------------------------------------------------------------------------#

@dataclass
class CacheInfo:
    """Information about the cache for the normalization.

    The normalization engine caches the normalized model so that it
    does not re-normalize when the requirements have not changed.
    This data class records the cache status.

    Attributes:
        status: The cache status (one of the ``CACHE_*``
            constants).
        cache_key: The key used for caching (a hash of the
            input requirements).
        cached_at: The timestamp when the cache was created
            (ISO format string).
        hit: Whether the cache was hit (``True`` if the
            normalized model was served from cache).
        requirements_hash: The hash of the input requirements.
    """

    status: str = CACHE_DISABLED
    cache_key: str = ""
    cached_at: str = ""
    hit: bool = False
    requirements_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "cache_key": self.cache_key,
            "cached_at": self.cached_at,
            "hit": self.hit,
            "requirements_hash": self.requirements_hash,
        }


# ---------------------------------------------------------------------------#
# Normalization provenance
# ---------------------------------------------------------------------------#

@dataclass
class NormalizationProvenance:
    """Records which data sources were used to build the
    Normalization Report.

    Attributes:
        request_available: Whether the user request was
            available.
        requirement_intelligence_available: Whether the
            requirement intelligence report was available.
        semantic_understanding_available: Whether the
            semantic understanding report was available.
        project_context_available: Whether the project
            context was available.
        knowledge_base_available: Whether the knowledge base
            was available.
        all_sources_used: The list of all source artefact
            identifiers that contributed to the report.
        request_summary: A short summary of the user request.
        requirement_count_from_intelligence: The number of
            requirements from the requirement intelligence
            report.
        intent_kind: The intent kind from the semantic
            understanding report.
        semantic_confidence: The confidence from the
            semantic understanding report.
        normalized_request: The normalized request from the
            semantic understanding report.
    """

    request_available: bool = False
    requirement_intelligence_available: bool = False
    semantic_understanding_available: bool = False
    project_context_available: bool = False
    knowledge_base_available: bool = False
    all_sources_used: List[str] = field(default_factory=list)
    request_summary: str = ""
    requirement_count_from_intelligence: int = 0
    intent_kind: str = ""
    semantic_confidence: float = 0.0
    normalized_request: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_available": self.request_available,
            "requirement_intelligence_available":
                self.requirement_intelligence_available,
            "semantic_understanding_available":
                self.semantic_understanding_available,
            "project_context_available": self.project_context_available,
            "knowledge_base_available": self.knowledge_base_available,
            "all_sources_used": list(self.all_sources_used),
            "request_summary": self.request_summary,
            "requirement_count_from_intelligence":
                self.requirement_count_from_intelligence,
            "intent_kind": self.intent_kind,
            "semantic_confidence": self.semantic_confidence,
            "normalized_request": self.normalized_request,
        }


# ---------------------------------------------------------------------------#
# Canonical (Normalized) Requirement
# ---------------------------------------------------------------------------#

@dataclass
class NormalizedRequirement:
    """A single, canonical (normalized) requirement.

    This is the core data class of the Normalized Requirement Model.
    Each requirement from the user's request is converted into a
    :class:`NormalizedRequirement` with a canonical ID, a canonical
    description, a unified category, a priority, links to features and
    components, dependencies, and an expected output.

    Attributes:
        id: A unique, machine-readable identifier (e.g.
            ``"NREQ-001"``).
        original_id: The original ID from the requirement
            intelligence report (if available).
        name: The canonical, machine-readable name (snake_case).
        display_name: The human-readable display name.
        description: The canonical, normalized description.
        category: The unified category (one of the
            ``CATEGORY_*`` constants).
        priority: The priority (one of the ``PRIORITY_*``
            constants).
        status: The status (one of the ``STATUS_*`` constants).
        feature: The feature this requirement belongs to.
        component: The component this requirement belongs to.
        dependencies: The list of requirement IDs this
            requirement depends on.
        expected_output: The expected output of this
            requirement.
        original_forms: The different forms this requirement
            appeared in (before normalization).
        source_artefact: The artefact this requirement was
            derived from.
    """

    id: str = ""
    original_id: str = ""
    name: str = ""
    display_name: str = ""
    description: str = ""
    category: str = CATEGORY_FUNCTIONAL
    priority: str = PRIORITY_MEDIUM
    status: str = STATUS_ACTIVE
    feature: str = ""
    component: str = ""
    dependencies: List[str] = field(default_factory=list)
    expected_output: str = ""
    original_forms: List[str] = field(default_factory=list)
    source_artefact: str = SOURCE_USER_REQUEST

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "original_id": self.original_id,
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
            "original_forms": list(self.original_forms),
            "source_artefact": self.source_artefact,
        }


# ---------------------------------------------------------------------------#
# The full Normalization Report (Normalized Requirement Model)
# ---------------------------------------------------------------------------#

@dataclass
class NormalizationReport:
    """The complete, authoritative output of the Requirement
    Normalization Engine.

    This is the **only** object the engine produces.  It is stored in
    the generation context as the ``requirement_normalization_report``
    artefact and becomes the unified reference for all following
    engines.

    The report contains:
    * The normalized requirements (the canonical model).
    * The canonical names (unified component/feature/module names).
    * The terminology mappings (unified terms).
    * The requirement links (feature, component, dependency, expected
      output).
    * The duplicate records (duplicates that were removed).
    * The conflict records (conflicts that were detected).
    * The cache info (cache status for performance).
    * The findings.
    * The provenance (traceability).

    Attributes:
        requirements: The list of :class:`NormalizedRequirement`
            objects — the canonical model.
        canonical_names: The list of :class:`CanonicalName`
            objects (unified names).
        terminology_mappings: The list of
            :class:`TerminologyMapping` objects (unified terms).
        links: The list of :class:`RequirementLink` objects
            (requirement → feature/component/dependency/output).
        duplicates: The list of :class:`DuplicateRecord`
            objects (duplicates removed).
        conflicts: The list of :class:`ConflictRecord`
            objects (conflicts detected).
        cache_info: The :class:`CacheInfo` — cache status.
        findings: The list of :class:`NormalizationFinding`
            objects.
        provenance: The :class:`NormalizationProvenance` —
            traceability record.
        summary: A human-readable summary.
        notes: General notes about the report.
        warnings: Warnings produced during report building.
        original_request: The original, unmodified request.
        normalized_request: The fully normalized request.
        confidence: 0.0–1.0 confidence in the normalization.
        confidence_level: The confidence level (one of the
            ``CONFIDENCE_*`` constants).
    """

    requirements: List[NormalizedRequirement] = field(default_factory=list)
    canonical_names: List[CanonicalName] = field(default_factory=list)
    terminology_mappings: List[TerminologyMapping] = \
        field(default_factory=list)
    links: List[RequirementLink] = field(default_factory=list)
    duplicates: List[DuplicateRecord] = field(default_factory=list)
    conflicts: List[ConflictRecord] = field(default_factory=list)
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    findings: List[NormalizationFinding] = field(default_factory=list)
    provenance: NormalizationProvenance = \
        field(default_factory=NormalizationProvenance)
    summary: str = ""
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    original_request: str = ""
    normalized_request: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW

    # -- convenience -------------------------------------------------------#

    @property
    def requirement_count(self) -> int:
        return len(self.requirements)

    @property
    def active_requirement_count(self) -> int:
        return sum(
            1 for r in self.requirements if r.status == STATUS_ACTIVE
        )

    @property
    def canonical_name_count(self) -> int:
        return len(self.canonical_names)

    @property
    def terminology_mapping_count(self) -> int:
        return len(self.terminology_mappings)

    @property
    def link_count(self) -> int:
        return len(self.links)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicates)

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def error_count(self) -> int:
        return sum(
            1 for f in self.findings if f.severity == SEVERITY_ERROR
        )

    @property
    def warning_count(self) -> int:
        return sum(
            1 for f in self.findings if f.severity == SEVERITY_WARNING
        )

    @property
    def has_duplicates(self) -> bool:
        return self.duplicate_count > 0

    @property
    def has_conflicts(self) -> bool:
        return self.conflict_count > 0

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    @property
    def has_unresolved_conflicts(self) -> bool:
        return any(
            c.resolution == "unresolved" for c in self.conflicts
        )

    @property
    def is_empty(self) -> bool:
        return self.requirement_count == 0

    @property
    def all_linked(self) -> bool:
        """``True`` when every active requirement has a feature or
        component link."""
        for req in self.requirements:
            if req.status != STATUS_ACTIVE:
                continue
            if not req.feature and not req.component:
                return False
        return True if self.requirement_count > 0 else False

    @property
    def has_sufficient_confidence(self) -> bool:
        """``True`` when the confidence is above the medium
        threshold."""
        return self.confidence >= CONFIDENCE_MEDIUM_THRESHOLD

    @property
    def ready(self) -> bool:
        """``True`` when the report is complete enough to proceed.

        The report is ready when:
        * There is at least one requirement.
        * All active requirements are linked (feature or component).
        * There are no error-level findings.
        * There are no unresolved conflicts.
        * The confidence is at or above the medium threshold.
        """
        return (
            self.requirement_count > 0
            and self.all_linked
            and not self.has_errors
            and not self.has_unresolved_conflicts
            and self.has_sufficient_confidence
        )

    @property
    def cache_hit(self) -> bool:
        return self.cache_info.hit

    # -- look-up helpers --------------------------------------------------#

    def get_requirement(self, req_id: str) -> Optional[NormalizedRequirement]:
        """Return the requirement with the given ID, or ``None``."""
        for req in self.requirements:
            if req.id == req_id:
                return req
        return None

    def get_requirement_by_name(
        self, name: str,
    ) -> Optional[NormalizedRequirement]:
        """Return the requirement with the given name, or ``None``."""
        for req in self.requirements:
            if req.name == name:
                return req
        return None

    def sorted_requirements(self) -> List[NormalizedRequirement]:
        """Return all requirements sorted by priority (descending)."""
        return sorted(
            self.requirements,
            key=lambda r: PRIORITY_WEIGHTS.get(r.priority, 0),
            reverse=True,
        )

    def requirements_by_category(
        self, category: str,
    ) -> List[NormalizedRequirement]:
        """Return all requirements in the given category."""
        return [
            r for r in self.requirements if r.category == category
        ]

    def category_counts(self) -> Dict[str, int]:
        """Return a mapping of category → count."""
        counts: Dict[str, int] = {}
        for req in self.requirements:
            counts[req.category] = counts.get(req.category, 0) + 1
        return counts

    def priority_counts(self) -> Dict[str, int]:
        """Return a mapping of priority → count."""
        counts: Dict[str, int] = {}
        for req in self.requirements:
            counts[req.priority] = counts.get(req.priority, 0) + 1
        return counts

    def get_links_for_requirement(
        self, req_id: str,
    ) -> List[RequirementLink]:
        """Return all links for the given requirement ID."""
        return [
            link for link in self.links
            if link.requirement_id == req_id
        ]

    def get_canonical_name(
        self, original: str,
    ) -> Optional[CanonicalName]:
        """Return the canonical name that the given original form was
        mapped to, or ``None``."""
        for cn in self.canonical_names:
            if original in cn.original_forms or original == cn.canonical_form:
                return cn
        return None

    def get_canonical_term(self, original: str) -> Optional[str]:
        """Return the canonical term for the given original term, or
        ``None``."""
        for tm in self.terminology_mappings:
            if tm.original_term == original:
                return tm.canonical_term
        return None

    # -- finding management -----------------------------------------------#

    def add_finding(
        self,
        severity: str,
        code: str,
        message: str,
        affected: str = "",
        resolution_hint: str = "",
        category: str = "validation",
    ) -> None:
        """Add a finding to the report."""
        self.findings.append(NormalizationFinding(
            severity=severity,
            code=code,
            message=message,
            affected=affected,
            resolution_hint=resolution_hint,
            category=category,
        ))
        if severity == SEVERITY_WARNING:
            self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_count": self.requirement_count,
            "active_requirement_count": self.active_requirement_count,
            "canonical_name_count": self.canonical_name_count,
            "terminology_mapping_count": self.terminology_mapping_count,
            "link_count": self.link_count,
            "duplicate_count": self.duplicate_count,
            "conflict_count": self.conflict_count,
            "finding_count": self.finding_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "has_duplicates": self.has_duplicates,
            "has_conflicts": self.has_conflicts,
            "has_unresolved_conflicts": self.has_unresolved_conflicts,
            "all_linked": self.all_linked,
            "has_sufficient_confidence": self.has_sufficient_confidence,
            "ready": self.ready,
            "cache_hit": self.cache_hit,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "summary": self.summary,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
            "original_request": self.original_request,
            "normalized_request": self.normalized_request,
            "requirements": [r.to_dict() for r in self.requirements],
            "canonical_names": [cn.to_dict() for cn in self.canonical_names],
            "terminology_mappings": [
                tm.to_dict() for tm in self.terminology_mappings
            ],
            "links": [l.to_dict() for l in self.links],
            "duplicates": [d.to_dict() for d in self.duplicates],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "cache_info": self.cache_info.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "provenance": self.provenance.to_dict(),
        }


__all__ = [
    # Source-artefact constants
    "SOURCE_USER_REQUEST",
    "SOURCE_REQUIREMENT_INTELLIGENCE",
    "SOURCE_SEMANTIC_UNDERSTANDING",
    "SOURCE_PROJECT_CONTEXT",
    "SOURCE_KNOWLEDGE_BASE",
    "ALL_SOURCES",
    # Severity constants
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "ALL_SEVERITIES",
    # Status constants
    "STATUS_ACTIVE",
    "STATUS_DEPRECATED",
    "STATUS_MERGED",
    "STATUS_REMOVED",
    "ALL_STATUSES",
    # Priority constants
    "PRIORITY_CRITICAL",
    "PRIORITY_HIGH",
    "PRIORITY_MEDIUM",
    "PRIORITY_LOW",
    "ALL_PRIORITIES",
    "PRIORITY_WEIGHTS",
    # Category constants
    "CATEGORY_FUNCTIONAL",
    "CATEGORY_NON_FUNCTIONAL",
    "CATEGORY_TECHNICAL",
    "CATEGORY_CONSTRAINT",
    "CATEGORY_INTERFACE",
    "CATEGORY_SECURITY",
    "CATEGORY_PERFORMANCE",
    "CATEGORY_USABILITY",
    "CATEGORY_DEPLOYMENT",
    "ALL_CATEGORIES",
    # Link kind constants
    "LINK_KIND_FEATURE",
    "LINK_KIND_COMPONENT",
    "LINK_KIND_DEPENDENCY",
    "LINK_KIND_EXPECTED_OUTPUT",
    "ALL_LINK_KINDS",
    # Cache status constants
    "CACHE_HIT",
    "CACHE_MISS",
    "CACHE_STALE",
    "CACHE_DISABLED",
    "ALL_CACHE_STATUSES",
    # Confidence level constants
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "ALL_CONFIDENCE_LEVELS",
    "CONFIDENCE_HIGH_THRESHOLD",
    "CONFIDENCE_MEDIUM_THRESHOLD",
    # Data model
    "CanonicalName",
    "TerminologyMapping",
    "RequirementLink",
    "DuplicateRecord",
    "ConflictRecord",
    "NormalizationFinding",
    "CacheInfo",
    "NormalizationProvenance",
    "NormalizedRequirement",
    "NormalizationReport",
]
