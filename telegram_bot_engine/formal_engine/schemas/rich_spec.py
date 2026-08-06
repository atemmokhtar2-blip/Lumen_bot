"""
RichSpec — the deep structured specification emitted by the AI SpecTranslator.

This is the SINGLE source of truth that flows into the code-generation pipeline.
Unlike the old lossy round-trip (JSON → sectioned text → regex re-parse),
RichSpec carries richly-typed fields that the downstream stages consume directly:

  RichSpec
    ├─ commands:   list[RichCommand]   (kind, collects_fields, post_action, entity, evidence, flow_steps)
    ├─ buttons:    list[RichButton]    (label, callback_id, target_command, evidence)
    ├─ entities:   list[RichEntity]    (name, fields with types, relations, evidence)
    ├─ rules:      list[RichRule]      (condition, effect, evidence)
    ├─ flows:      list[RichFlow]      (name, ordered steps)
    ├─ permissions: list[RichPermission]
    └─ evidence:   RichEvidence        (global traceability to user text)

Design principles (zero hardcoded templates):
  - Every command carries an explicit ``kind`` chosen by the AI from the user's
    intent — the engine NEVER classifies with hardcoded verb/stem lists.
  - Every command carries ``collects_fields`` and ``post_action`` so the
    transpiler knows exactly what to generate without guessing.
  - Every item carries ``evidence`` — a verbatim quote from the user request —
    so the grounding gate can verify provenance without synonym dictionaries.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RichModel(BaseModel):
    """Base for all RichSpec models — frozen, no extras, whitespace stripped."""
    model_config = ConfigDict(
        frozen=True,
        extra="ignore",  # tolerate extra keys from the LLM rather than crash
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class CommandKind(str, Enum):
    """How a command interacts with data — chosen by the AI, not by stem matching."""
    START = "start"
    HELP = "help"
    COLLECT = "collect"          # gathers fields from the user (a wizard)
    LOOKUP = "lookup"            # queries existing records
    LIST = "list"                # lists / browses records
    STATS = "stats"              # aggregate / dashboard numbers
    BROADCAST = "broadcast"      # admin sends to many users
    ACTION = "action"            # performs a side-effect (send, notify, toggle)
    INFO = "info"                # static informational reply
    NAVIGATE = "navigate"        # opens a menu / keyboard
    CUSTOM = "custom"            # anything the AI explicitly describes


class PostAction(str, Enum):
    """What happens after a command finishes collecting data."""
    STORE = "store"              # persist into the entity store
    CONFIRM = "confirm"          # echo back the collected data
    NOTIFY = "notify"            # send a notification
    COMPUTE = "compute"          # run a calculation and reply
    NONE = "none"                # no post-action


class FieldType(str, Enum):
    STR = "str"
    INT = "int"
    BOOL = "bool"
    FLOAT = "float"
    LIST = "list"
    DICT = "dict"
    OPTIONAL_STR = "str|none"
    OPTIONAL_INT = "int|none"


class RichEvidence(RichModel):
    """Traceability anchor — a verbatim snippet from the user request."""
    quote: str = Field(default="", description="Verbatim phrase from the user request that justifies this item")
    section: str = Field(default="", description="Logical section label the AI assigned")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class RichField(RichModel):
    name: str
    field_type: FieldType = FieldType.STR
    prompt: str = ""             # human-facing prompt shown during a wizard
    required: bool = True
    evidence: RichEvidence = Field(default_factory=RichEvidence)


class RichEntity(RichModel):
    name: str
    fields: list[RichField] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list, description="Names of related entities")
    evidence: RichEvidence = Field(default_factory=RichEvidence)

    @field_validator("name")
    @classmethod
    def _norm_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("entity name empty")
        return v[0].upper() + v[1:] if v[0].isalpha() else v


class RichFlowStep(RichModel):
    key: str = Field(description="Field key collected at this step, or action label")
    prompt: str = Field(default="", description="Message shown to the user at this step")
    action: str = Field(default="ask", description="ask | confirm | compute | notify | done")


class RichCommand(RichModel):
    name: str = Field(..., min_length=1, max_length=32)
    description: str = ""
    admin_only: bool = False
    kind: CommandKind = CommandKind.CUSTOM
    entity: str = Field(default="", description="Entity this command operates on (if any)")
    collects_fields: list[str] = Field(default_factory=list, description="Field keys gathered from the user")
    post_action: PostAction = PostAction.NONE
    reply_text: str = Field(default="", description="Static reply for info/start/help commands")
    flow_steps: list[RichFlowStep] = Field(default_factory=list)
    evidence: RichEvidence = Field(default_factory=RichEvidence)

    @field_validator("name")
    @classmethod
    def _cmd(cls, v: str) -> str:
        v = v.lower().lstrip("/")
        if not v.replace("_", "").isalnum():
            raise ValueError(f"invalid command name: {v}")
        return v


class RichButton(RichModel):
    label: str = Field(..., min_length=1, max_length=64)
    callback_id: str = Field(..., min_length=1, max_length=64)
    target_command: str = Field(default="", description="Command triggered when this button is pressed")
    evidence: RichEvidence = Field(default_factory=RichEvidence)

    @field_validator("callback_id")
    @classmethod
    def _cb(cls, v: str) -> str:
        v = v.lower().strip().replace(" ", "_")
        if not v.replace("_", "").isalnum():
            raise ValueError(f"invalid callback_id: {v}")
        return v


class RichRule(RichModel):
    name: str = ""
    condition: str = Field(..., description="Natural-language condition the AI extracted")
    effect: str = Field(..., description="Natural-language effect / action to take")
    evidence: RichEvidence = Field(default_factory=RichEvidence)


class RichFlow(RichModel):
    name: str
    steps: list[RichFlowStep] = Field(default_factory=list)


class RichPermission(RichModel):
    role: str = "user"
    allows: list[str] = Field(default_factory=list, description="Command names this role may invoke")


class RichTechFlags(RichModel):
    database: str = "sqlite"      # sqlite | postgres | none
    payments: bool = False
    admin_panel: bool = False
    async_queue: bool = False
    file_handling: bool = False
    state_management: bool = True
    notifications: bool = False


class RichSpec(RichModel):
    """The deep structured spec — AI output, engine input."""

    schema_version: str = "2.0"
    bot_name: str = Field(..., min_length=2, max_length=64)
    bot_kind: str = "custom"
    description: str = ""
    language: str = "ar"

    commands: list[RichCommand] = Field(default_factory=list)
    buttons: list[RichButton] = Field(default_factory=list)
    entities: list[RichEntity] = Field(default_factory=list)
    rules: list[RichRule] = Field(default_factory=list)
    flows: list[RichFlow] = Field(default_factory=list)
    permissions: list[RichPermission] = Field(default_factory=list)

    tech: RichTechFlags = Field(default_factory=RichTechFlags)
    hard_constraints: list[str] = Field(default_factory=list)
    evidence: RichEvidence = Field(default_factory=RichEvidence)

    # ------------------------------------------------------------------ helpers
    def command_names(self) -> list[str]:
        return [c.name for c in self.commands]

    def entity_names(self) -> list[str]:
        return [e.name for e in self.entities]

    def has_database(self) -> bool:
        if self.tech.database == "none":
            return False
        return bool(self.entities) or self.tech.database != "none"

    def get_entity(self, name: str) -> RichEntity | None:
        if not name:
            return None
        low = name.lower()
        for e in self.entities:
            if e.name.lower() == low:
                return e
        return None

    def ensure_minimums(self) -> "RichSpec":
        """Return a copy with /start and /help guaranteed (pure data fix)."""
        names = set(self.command_names())
        cmds = list(self.commands)
        changed = False
        if "start" not in names:
            cmds.insert(0, RichCommand(
                name="start",
                kind=CommandKind.START,
                reply_text=f"أهلاً بك في بوت {self.bot_name}! استخدم /help لمعرفة الأوامر.",
                description="start",
            ))
            changed = True
        if "help" not in names:
            cmds.append(RichCommand(
                name="help",
                kind=CommandKind.HELP,
                description="help",
            ))
            changed = True
        if not changed:
            return self
        return self.model_copy(update={"commands": cmds})


class RichSpecValidation(RichModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def validate_rich_spec(spec: RichSpec) -> RichSpecValidation:
    """Structural validation — no domain assumptions."""
    errors: list[str] = []
    warnings: list[str] = []
    if not spec.bot_name.strip():
        errors.append("bot_name empty")
    names = spec.command_names()
    if not names:
        errors.append("no commands")
    seen_cmd = set()
    for c in spec.commands:
        if c.name in seen_cmd:
            errors.append(f"duplicate command: {c.name}")
        seen_cmd.add(c.name)
    seen_cb = set()
    for b in spec.buttons:
        if b.callback_id in seen_cb:
            errors.append(f"duplicate callback_id: {b.callback_id}")
        seen_cb.add(b.callback_id)
    # Entity field checks (structural, not domain)
    for e in spec.entities:
        if not e.fields:
            warnings.append(f"entity {e.name} has no fields")
        seen_f = set()
        for f in e.fields:
            if f.name in seen_f:
                warnings.append(f"entity {e.name} duplicate field {f.name}")
            seen_f.add(f.name)
    # Commands referencing unknown entities
    ent_names = {e.name.lower() for e in spec.entities}
    for c in spec.commands:
        if c.entity and c.entity.lower() not in ent_names:
            warnings.append(f"command /{c.name} references unknown entity {c.entity}")
    return RichSpecValidation(ok=len(errors) == 0, errors=errors, warnings=warnings)


def rich_spec_from_dict(data: dict[str, Any]) -> RichSpec:
    """Parse a raw LLM JSON dict into a validated RichSpec, applying safe defaults."""
    if not isinstance(data, dict):
        raise ValueError("spec payload is not a dict")
    # Ensure minimums so downstream never sees an empty bot
    spec = RichSpec.model_validate(data)
    spec = spec.ensure_minimums()
    return spec
