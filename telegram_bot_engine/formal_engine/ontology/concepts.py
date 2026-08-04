"""Concept & Registry – high-precision matching optimized for long texts."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from .base import ConceptKind, OntologyID, RelationType, StrictModel


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


class Concept(StrictModel):
    id: OntologyID = Field(default_factory=OntologyID)
    kind: ConceptKind
    canonical_name: str = Field(..., min_length=1, max_length=128)
    labels: dict[str, str] = Field(default_factory=dict)
    definition: str = Field(..., min_length=5)
    synonyms: list[str] = Field(default_factory=list)
    surface_forms: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("canonical_name")
    @classmethod
    def normalize_canonical(cls, v: str) -> str:
        return v.strip().lower().replace(" ", "_")

    def all_forms(self) -> list[str]:
        forms = {self.canonical_name}
        forms.update(normalize(s) for s in self.synonyms if s)
        forms.update(normalize(s) for s in self.surface_forms if s)
        forms.update(normalize(v) for v in self.labels.values() if v)
        return sorted(f for f in forms if len(f) >= 2)


class Relation(StrictModel):
    source_id: OntologyID
    target_id: OntologyID
    relation_type: RelationType
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConceptRegistry(StrictModel):
    concepts: dict[str, Concept] = Field(default_factory=dict)
    relations: list[Relation] = Field(default_factory=list)
    _form_index: dict[str, list[str]] = {}

    def finalize(self) -> None:
        index: dict[str, list[str]] = {}
        for name, concept in self.concepts.items():
            for form in concept.all_forms():
                index.setdefault(form, []).append(name)
        object.__setattr__(self, "_form_index", index)

    def get(self, canonical_name: str) -> Concept | None:
        return self.concepts.get(canonical_name.lower())

    def find_matching(self, text: str) -> list[Concept]:
        text_norm = normalize(text)
        found: set[str] = set()
        for form, names in self._form_index.items():
            if form in text_norm:
                found.update(names)
        # Line-level for better Arabic phrase capture
        for line in text.splitlines():
            line_n = normalize(line)
            for form, names in self._form_index.items():
                if len(form) >= 3 and form in line_n:
                    found.update(names)
        return [self.concepts[n] for n in found if n in self.concepts]

    def requires(self, concept: Concept) -> list[Concept]:
        ids = {
            r.target_id
            for r in self.relations
            if r.source_id == concept.id and r.relation_type == RelationType.REQUIRES
        }
        return [c for c in self.concepts.values() if c.id in ids]
