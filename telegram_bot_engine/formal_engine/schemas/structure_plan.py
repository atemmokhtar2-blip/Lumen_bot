"""
StructurePlan — Phase 0 contract.

Structure Engine (future) may emit ONLY a project skeleton and manifest.
It MUST NOT write business logic or domain packs.

Everything in this plan is derived from the user-grounded formal contract:
commands, entities, buttons, flows. No shop/ticket/ecommerce templates.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class FileRole(str, Enum):
    """Structural roles only — not domain features."""

    ENTRY = "entry"  # main.py / __main__
    CONFIG = "config"
    MODELS = "models"
    HANDLERS = "handlers"
    SERVICES = "services"
    STORAGE = "storage"
    UTILS = "utils"
    REQUIREMENTS = "requirements"
    README = "readme"
    ENV_EXAMPLE = "env_example"
    OTHER = "other"


class FileStubKind(str, Enum):
    """How empty the structure file is before Code Engine fills it."""

    EMPTY = "empty"  # zero bytes / placeholder only
    SIGNATURES = "signatures"  # def/class signatures, body pass
    WIRED = "wired"  # fully implemented (legacy monolithic path)


class PlannedFile(StrictModel):
    """One file in the future structure tree."""

    path: str = Field(..., min_length=1, description="Relative path from project root")
    role: FileRole = FileRole.OTHER
    stub_kind: FileStubKind = FileStubKind.WIRED
    description: str = ""
    # Links to user-grounded contract only
    binds_commands: list[str] = Field(default_factory=list)
    binds_entities: list[str] = Field(default_factory=list)
    binds_buttons: list[str] = Field(default_factory=list)
    binds_flows: list[str] = Field(default_factory=list)
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class StructurePlan(StrictModel):
    """
    Complete structural blueprint for a generated bot project.

    Phase 0: derived for observation/metadata only; does not change transpile output.
    Later: Structure Engine materializes stubs; Code Engine fills bodies.
    """

    bot_name: str = ""
    # Relative paths that must exist after structure stage
    files: list[PlannedFile] = Field(default_factory=list)
    # Contract snapshot (names only — from user text / DSL, never invented packs)
    command_names: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    button_labels: list[str] = Field(default_factory=list)
    flow_ids: list[str] = Field(default_factory=list)
    # Schema version for forward compatibility
    schema_version: str = "0.1.0"
    notes: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def paths(self) -> list[str]:
        return [f.path for f in self.files]

    def required_paths(self) -> list[str]:
        return [f.path for f in self.files if f.required]


class StructureGateResult(StrictModel):
    """Outcome of validating a StructurePlan (Phase 1+)."""

    ok: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
