"""
Knowledge base reader — reads the knowledge base from the generation
context.

The :class:`KnowledgeReader` is responsible for obtaining the
``knowledge_base`` artefact (if present) from the generation context
and returning a normalised :class:`KnowledgeData` object.

The knowledge base is a free-form dictionary of pre-approved
assumptions and domain knowledge.  When it is not present the reader
returns a :class:`KnowledgeData` with ``available=False``.

This module is a pure reader: it has no side effects and does not
modify the generation context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ....core.context import GenerationContext
from .report_data import SOURCE_KNOWLEDGE_BASE


# ---------------------------------------------------------------------------#
# Knowledge data
# ---------------------------------------------------------------------------#

@dataclass
class KnowledgeData:
    """Normalised view of the knowledge base.

    The knowledge base is a free-form dictionary.  The reader extracts
    common keys that the Semantic Understanding Engine uses, while
    keeping the full dictionary available for custom look-ups.

    Attributes:
        assumptions: The list of pre-approved assumptions.  Each
            assumption is a string describing a default that may be
            applied when the user does not provide the information.
        defaults: A dictionary of default values keyed by field
            name (e.g. ``{"database": "sqlite"}``).
        domain_rules: A list of domain-specific rules that
            constrain the understanding.
        constraints: A list of project-level constraints that
            must be respected.
        synonyms: A dictionary of synonym mappings (word →
            canonical form) that the engine may use to resolve
            synonyms.
        abbreviations: A dictionary of abbreviation mappings
            (abbreviation → expanded form) that the engine may use.
        raw: The raw knowledge base dictionary (for custom
            look-ups).
        keys: The list of top-level keys in the knowledge base.
        available: Whether the knowledge base was available.
    """

    assumptions: List[str] = field(default_factory=list)
    defaults: Dict[str, Any] = field(default_factory=dict)
    domain_rules: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    synonyms: Dict[str, str] = field(default_factory=dict)
    abbreviations: Dict[str, str] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)
    keys: List[str] = field(default_factory=list)
    available: bool = False

    @property
    def source_artefact(self) -> str:
        return SOURCE_KNOWLEDGE_BASE

    def get(self, key: str, default: Any = None) -> Any:
        """Look up a key in the raw knowledge base."""
        return self.raw.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assumptions": list(self.assumptions),
            "defaults": dict(self.defaults),
            "domain_rules": list(self.domain_rules),
            "constraints": list(self.constraints),
            "synonyms": dict(self.synonyms),
            "abbreviations": dict(self.abbreviations),
            "keys": list(self.keys),
            "available": self.available,
        }


class KnowledgeReader:
    """Reads the knowledge base from the generation context.

    The reader looks for the ``knowledge_base`` artefact.  When
    present, it extracts the common keys (assumptions, defaults,
    domain rules, constraints, synonyms, abbreviations) and keeps the
    full dictionary.  When absent, it returns a
    :class:`KnowledgeData` with ``available=False``.
    """

    def read(self, context: GenerationContext) -> KnowledgeData:
        """Read the knowledge base and return a :class:`KnowledgeData`."""
        knowledge_base = context.get("knowledge_base")
        if knowledge_base is None:
            return KnowledgeData(available=False)

        if isinstance(knowledge_base, dict):
            raw = knowledge_base
        elif hasattr(knowledge_base, "to_dict"):
            raw = knowledge_base.to_dict()
        else:
            # Try to use it as a mapping.
            try:
                raw = dict(knowledge_base)
            except (TypeError, ValueError):
                return KnowledgeData(available=False)

        assumptions = self._as_string_list(raw.get("assumptions", []))
        defaults = raw.get("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}
        domain_rules = self._as_string_list(raw.get("domain_rules", []))
        constraints = self._as_string_list(raw.get("constraints", []))
        synonyms = raw.get("synonyms", {})
        if not isinstance(synonyms, dict):
            synonyms = {}
        abbreviations = raw.get("abbreviations", {})
        if not isinstance(abbreviations, dict):
            abbreviations = {}
        keys = list(raw.keys())

        return KnowledgeData(
            assumptions=assumptions,
            defaults=defaults,
            domain_rules=domain_rules,
            constraints=constraints,
            synonyms=synonyms,
            abbreviations=abbreviations,
            raw=raw,
            keys=keys,
            available=True,
        )

    @staticmethod
    def _as_string_list(value: Any) -> List[str]:
        """Convert a value to a list of strings."""
        if isinstance(value, (list, tuple)):
            return [str(v) for v in value if v is not None]
        if isinstance(value, str):
            return [value]
        return []


__all__ = ["KnowledgeReader", "KnowledgeData"]
