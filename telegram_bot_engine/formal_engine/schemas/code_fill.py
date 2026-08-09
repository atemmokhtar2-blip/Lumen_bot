"""
CodeFillRequest / CodeFillResult — Phase 0 contract.

Code Engine (future) fills one structured file at a time from the formal contract.
It MUST NOT invent commands, entities, or domain packs.
It MUST NOT re-parse free-form user prose (contract-only).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .structure_plan import FileRole, PlannedFile, StructurePlan


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class CodeFillRequest(StrictModel):
    """
    Ask Code Engine to produce the body of exactly one planned file.

    Inputs are structural + contract slices only — no raw NL reinterpretation.
    """

    plan: StructurePlan
    target: PlannedFile
    # Opaque formal slices (JSON-serializable) already grounded upstream
    commands: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    buttons: list[dict[str, Any]] = Field(default_factory=list)
    flows: list[dict[str, Any]] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    # Optional IR blobs (inference wizards, tools) — still user-grounded upstream
    ir_extra: dict[str, Any] = Field(default_factory=dict)

    def role(self) -> FileRole:
        return self.target.role

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CodeFillResult(StrictModel):
    """Output of filling one file."""

    path: str
    content: str = ""
    ok: bool = True
    errors: list[str] = Field(default_factory=list)
    # Which contract names were actually emitted into this file
    used_commands: list[str] = Field(default_factory=list)
    used_entities: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CodeEngineBatchResult(StrictModel):
    """Aggregate result after filling all planned files."""

    files: list[CodeFillResult] = Field(default_factory=list)
    ok: bool = True
    errors: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
