"""
ProgramContract — the ONLY interface between Understanding Service and Codegen Service.

Understanding Service:
  - reads natural language
  - MUST emit ProgramContract
  - MUST NOT write project files

Codegen Service:
  - reads ProgramContract only (blind to raw user text)
  - MUST emit project files
  - MUST NOT re-interpret natural language

This is the strongest practical contract for deterministic bot assembly.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class BotKind(str, Enum):
    UTILITY = "utility"
    ECOMMERCE = "ecommerce"
    ADMIN = "admin"
    COMMUNITY = "community"
    TICKETING = "ticketing"
    GAME = "game"
    ASSISTANT = "assistant"
    DOCUMENT = "document"
    NOTIFICATION = "notification"
    BOOKING = "booking"
    CUSTOM = "custom"


class HandlerKind(str, Enum):
    COMMAND = "command"
    CALLBACK = "callback"
    MESSAGE = "message"
    CONVERSATION = "conversation"


class FieldType(str, Enum):
    STR = "str"
    INT = "int"
    BOOL = "bool"
    FLOAT = "float"
    LIST = "list"
    DICT = "dict"
    OPTIONAL_STR = "str | None"
    OPTIONAL_INT = "int | None"


class CommandUnit(StrictModel):
    name: str = Field(..., min_length=1, max_length=32)
    description: str = ""
    admin_only: bool = False

    @field_validator("name")
    @classmethod
    def _cmd(cls, v: str) -> str:
        v = v.lower().lstrip("/")
        if not v.replace("_", "").isalnum():
            raise ValueError(f"invalid command name: {v}")
        return v


class ButtonUnit(StrictModel):
    label: str = Field(..., min_length=1, max_length=64)
    callback_id: str = Field(..., min_length=1, max_length=64)


class HandlerUnit(StrictModel):
    id: str
    kind: HandlerKind
    triggers: list[str] = Field(default_factory=list)
    admin_only: bool = False
    description: str = ""


class FieldUnit(StrictModel):
    name: str
    field_type: FieldType = FieldType.STR


class EntityUnit(StrictModel):
    name: str
    fields: list[FieldUnit] = Field(default_factory=list)


class ServiceUnit(StrictModel):
    name: str
    responsibility: str = ""


class FlowStep(StrictModel):
    id: str
    action: str
    next_id: str | None = None


class FlowUnit(StrictModel):
    name: str
    steps: list[FlowStep] = Field(default_factory=list)


class PermissionUnit(StrictModel):
    role: str  # user | admin | owner
    allows: list[str] = Field(default_factory=list)  # command names or callback ids


class ConversationStateUnit(StrictModel):
    name: str
    prompt: str = ""
    next_state: str | None = None
    collects_field: str | None = None



class TechFlags(StrictModel):
    database: str = "sqlite"  # sqlite | postgres | none
    payments: bool = False
    admin_panel: bool = False
    async_queue: bool = False
    file_handling: bool = False
    state_management: bool = True


class QualityFlags(StrictModel):
    high_performance: bool = True
    full_error_handling: bool = True
    concurrent_users: bool = False
    modular_code: bool = True


class ProgramContract(StrictModel):
    """
    Strong program contract — codegen input, understanding output.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)

    schema_version: str = "1.0"
    bot_name: str = Field(..., min_length=2, max_length=64)
    bot_kind: BotKind = BotKind.CUSTOM
    version: str = "1.0.0"

    # Optional human summary for README only — never used for control flow in codegen
    summary: str = ""

    commands: list[CommandUnit] = Field(default_factory=list)
    buttons: list[ButtonUnit] = Field(default_factory=list)
    handlers: list[HandlerUnit] = Field(default_factory=list)
    entities: list[EntityUnit] = Field(default_factory=list)
    services: list[ServiceUnit] = Field(default_factory=list)
    flows: list[FlowUnit] = Field(default_factory=list)
    permissions: list[PermissionUnit] = Field(default_factory=list)
    conversation_states: list[ConversationStateUnit] = Field(default_factory=list)

    integrations: list[str] = Field(default_factory=lambda: ["telegram"])
    feature_tags: list[str] = Field(default_factory=list)
    tech: TechFlags = Field(default_factory=TechFlags)
    quality: QualityFlags = Field(default_factory=QualityFlags)
    hard_constraints: list[str] = Field(default_factory=list)
    architecture_rules_applied: list[str] = Field(default_factory=list)

    def command_names(self) -> list[str]:
        return [c.name for c in self.commands]

    def ensure_minimums(self) -> "ProgramContract":
        """Return a copy with /start /help guaranteed (pure data fix)."""
        names = set(self.command_names())
        cmds = list(self.commands)
        if "start" not in names:
            cmds.insert(0, CommandUnit(name="start", description="start"))
        if "help" not in names:
            cmds.append(CommandUnit(name="help", description="help"))
        return self.model_copy(update={"commands": cmds})


class ContractValidation(StrictModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def validate_contract(contract: ProgramContract) -> ContractValidation:
    errors: list[str] = []
    warnings: list[str] = []
    if not contract.bot_name.strip():
        errors.append("bot_name empty")
    names = contract.command_names()
    if "start" not in names:
        errors.append("missing command: start")
    if "help" not in names:
        warnings.append("missing command: help")
    if not contract.buttons:
        warnings.append("no buttons — /start will show minimal UI")
    seen_cb = set()
    for b in contract.buttons:
        if b.callback_id in seen_cb:
            errors.append(f"duplicate callback_id: {b.callback_id}")
        seen_cb.add(b.callback_id)
        if len(b.callback_id.encode("utf-8")) > 64:
            errors.append(f"callback_id too long: {b.callback_id}")
    if contract.tech.payments and "Order" not in [e.name for e in contract.entities]:
        warnings.append("payments enabled but no Order entity")
    if contract.tech.admin_panel and "admin" not in names:
        warnings.append("admin_panel without /admin command")
    if contract.flows and not contract.conversation_states:
        warnings.append("flows present without conversation_states")
    entity_names = {e.name for e in contract.entities}
    for e in contract.entities:
        if not e.fields:
            warnings.append(f"entity {e.name} has no fields")
    if contract.tech.payments and "Payment" not in entity_names:
        warnings.append("payments without Payment entity")
    return ContractValidation(ok=len(errors) == 0, errors=errors, warnings=warnings)
