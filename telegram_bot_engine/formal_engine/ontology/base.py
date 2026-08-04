"""Ontological primitives – strict, immutable, production-grade."""

from __future__ import annotations

from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        use_enum_values=False,
    )


class OntologyID(StrictModel):
    value: UUID = Field(default_factory=uuid4)

    def __str__(self) -> str:
        return str(self.value)

    def __hash__(self) -> int:
        return hash(self.value)


class ConceptKind(str, Enum):
    BOT_CAPABILITY = "bot_capability"
    DOCUMENT_TYPE = "document_type"
    UI_ELEMENT = "ui_element"
    TECHNICAL_COMPONENT = "technical_component"
    QUALITY_ATTRIBUTE = "quality_attribute"
    DESIGN_TOKEN = "design_token"
    LANGUAGE_FEATURE = "language_feature"
    WORKFLOW_STEP = "workflow_step"
    CONSTRAINT = "constraint"
    EXTERNAL_SERVICE = "external_service"
    DATA_MODEL = "data_model"
    SECURITY_CONCERN = "security_concern"


class RelationType(str, Enum):
    REQUIRES = "requires"
    ENABLES = "enables"
    CONFLICTS_WITH = "conflicts_with"
    SPECIALIZES = "specializes"
    PART_OF = "part_of"
    USES = "uses"
    PRODUCES = "produces"
    CONSUMES = "consumes"
    ENHANCES = "enhances"
    IMPLEMENTS = "implements"
