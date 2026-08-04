"""
FormalBotSpec – General purpose formal specification for ANY Telegram bot.
Extreme precision, zero domain lock-in.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
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
    """A single concrete feature the bot must implement."""
    name: str
    description: str = ""
    priority: int = 50


class CommandSpec(StrictModel):
    command: str
    description: str
    admin_only: bool = False


class ButtonSpec(StrictModel):
    text: str
    callback_data: str


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
    """
    Complete formal specification of a Telegram bot.
    Domain-agnostic. Works for any bot type.
    """

    # Identity
    bot_name: str = Field(..., min_length=2, max_length=64)
    bot_type: BotType = BotType.CUSTOM
    version: str = "1.0"
    description: str = Field(default="", min_length=0)
    final_goal: str | None = None

    # Core capabilities (free-form canonical names from ontology)
    capabilities: list[str] = Field(default_factory=list)

    # Concrete features extracted from the text
    features: list[Feature] = Field(default_factory=list)

    # UI
    ui: UIFlow = Field(default_factory=UIFlow)

    # Languages
    languages: list[LanguageSupport] = Field(default_factory=lambda: [LanguageSupport.ARABIC])

    # Technical decisions
    database: DatabaseChoice = DatabaseChoice.SQLITE
    requires_async_queue: bool = False
    requires_state_management: bool = True
    requires_admin_panel: bool = False
    requires_payments: bool = False
    requires_file_handling: bool = False
    external_services: list[str] = Field(default_factory=list)

    # Quality
    quality: QualityRequirements = Field(default_factory=QualityRequirements)

    # Solver constraints
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)

    # Provenance
    source_sections: dict[str, str] = Field(default_factory=dict)

    def has_capability(self, name: str) -> bool:
        return name.lower() in {c.lower() for c in self.capabilities}

    def has_feature(self, name: str) -> bool:
        return name.lower() in {f.name.lower() for f in self.features}
