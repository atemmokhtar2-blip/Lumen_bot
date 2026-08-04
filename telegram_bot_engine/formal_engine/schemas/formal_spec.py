"""
FormalBotSpec — rich formal model produced by deep understanding.
Generation must assemble code FROM this model, not from fixed templates.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", validate_assignment=True, str_strip_whitespace=True
    )


class BotType(str, Enum):
    UTILITY = "utility"
    ECOMMERCE = "ecommerce"
    ADMIN = "admin"
    COMMUNITY = "community"
    TICKETING = "ticketing"
    GAME = "game"
    ASSISTANT = "assistant"
    DOCUMENT = "document"
    NOTIFICATION = "notification"
    CUSTOM = "custom"


class LanguageSupport(str, Enum):
    ARABIC = "ar"
    ARABIC_RTL = "ar_rtl"
    ENGLISH = "en"
    MIXED = "mixed"


class DatabaseChoice(str, Enum):
    POSTGRES = "postgres"
    SQLITE = "sqlite"
    NONE = "none"


class Feature(StrictModel):
    name: str
    feature_id: str = ""
    category: str = ""
    description: str = ""
    priority: int = 50


class CommandSpec(StrictModel):
    command: str
    description: str
    admin_only: bool = False


class ButtonSpec(StrictModel):
    text: str
    callback_data: str


class HandlerSpec(StrictModel):
    name: str
    handler_type: str  # command | callback | message | conversation
    triggers: list[str] = Field(default_factory=list)
    admin_only: bool = False
    description: str = ""


class FieldSpec(StrictModel):
    name: str
    type_hint: str = "str"


class DataModelSpec(StrictModel):
    name: str
    fields: list[str] = Field(default_factory=list)
    typed_fields: list[FieldSpec] = Field(default_factory=list)



class UIFlow(StrictModel):
    welcome_message: str = ""
    main_buttons: list[ButtonSpec] = Field(default_factory=list)
    commands: list[CommandSpec] = Field(default_factory=list)
    show_progress: bool = False


class QualityRequirements(StrictModel):
    high_performance: bool = True
    full_error_handling: bool = True
    concurrent_users: bool = False
    modular_code: bool = True
    high_availability: bool = False
    clean_extensible: bool = True


class FormalBotSpec(StrictModel):
    bot_name: str = Field(..., min_length=2, max_length=64)
    bot_type: BotType = BotType.CUSTOM
    version: str = "1.0"
    description: str = ""
    final_goal: str | None = None

    capabilities: list[str] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)
    feature_tags: list[str] = Field(default_factory=list)

    # Deep structure understood from the request + knowledge base
    handlers: list[HandlerSpec] = Field(default_factory=list)
    data_models: list[DataModelSpec] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)

    ui: UIFlow = Field(default_factory=UIFlow)
    languages: list[LanguageSupport] = Field(default_factory=lambda: [LanguageSupport.ARABIC])

    database: DatabaseChoice = DatabaseChoice.SQLITE
    requires_async_queue: bool = False
    requires_state_management: bool = True
    requires_admin_panel: bool = False
    requires_payments: bool = False
    requires_file_handling: bool = False
    external_services: list[str] = Field(default_factory=list)

    quality: QualityRequirements = Field(default_factory=QualityRequirements)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    architecture_rules_applied: list[str] = Field(default_factory=list)
    source_sections: dict[str, str] = Field(default_factory=dict)

    def has_feature_tag(self, tag: str) -> bool:
        return tag in self.feature_tags
