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
    action_type: str = Field(default="", description="Semantic action identifier (ban_user, mute_user, kick_user, pin_message, delete_messages, toggle_setting, set_welcome, set_rules, add_filter, show_stats, broadcast_message, show_admins, show_staff, show_id, show_info, report_user, set_language, show_settings, etc.) — drives real Telegram API calls in the transpiler")
    target_args: str = Field(default="", description="Natural-language description of arguments this command takes (e.g. 'user_id or reply to message', 'duration + reason') — used to guide the handler")
    evidence: RichEvidence = Field(default_factory=RichEvidence)

    @field_validator("name")
    @classmethod
    def _cmd(cls, v: str) -> str:
        v = v.lower().lstrip("/")
        if not v.replace("_", "").isalnum():
            raise ValueError(f"invalid command name: {v}")
        return v

    @field_validator("action_type")
    @classmethod
    def _norm_action_type(cls, v: str) -> str:
        v = (v or "").strip().lower().replace("-", "_").replace(" ", "_")
        if v and not v.replace("_", "").isalnum():
            # keep only alphanumeric + underscore
            import re as _re
            v = _re.sub(r"[^a-z0-9_]", "", v)
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


def _sanitize_enums(data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize enum values in raw data before validation.

    The AI translator sometimes produces invalid enum values (e.g. post_action='action'
    which is a CommandKind, not a PostAction). This maps them to valid values.
    """
    valid_kinds = {k.value for k in CommandKind}
    valid_post_actions = {k.value for k in PostAction}
    valid_field_types = {k.value for k in FieldType}

    # Map common AI mistakes for post_action
    post_action_fix = {
        "action": "none",      # 'action' is a CommandKind, not PostAction
        "save": "store",
        "persist": "store",
        "insert": "store",
        "create": "store",
        "send": "notify",
        "message": "notify",
        "calculate": "compute",
        "calc": "compute",
        "echo": "confirm",
        "display": "confirm",
        "show": "confirm",
        "default": "none",
        "": "none",
    }

    # Map common AI mistakes for kind
    kind_fix = {
        "wizard": "collect",
        "form": "collect",
        "input": "collect",
        "query": "lookup",
        "search": "lookup",
        "find": "lookup",
        "browse": "list",
        "show": "list",
        "display": "list",
        "dashboard": "stats",
        "statistics": "stats",
        "menu": "navigate",
        "page": "navigate",
        "static": "info",
        "information": "info",
        "": "custom",
    }

    commands = data.get("commands") or []
    if isinstance(commands, list):
        for c in commands:
            if not isinstance(c, dict):
                continue
            # Sanitize kind
            kind = (c.get("kind") or "").lower().strip()
            if kind and kind not in valid_kinds:
                c["kind"] = kind_fix.get(kind, "custom")
            elif not kind:
                c["kind"] = "custom"
            # Sanitize post_action
            pa = (c.get("post_action") or "").lower().strip()
            if pa and pa not in valid_post_actions:
                c["post_action"] = post_action_fix.get(pa, "none")
            elif not pa:
                c["post_action"] = "none"

    # Sanitize entity field types
    entities = data.get("entities") or []
    if isinstance(entities, list):
        for e in entities:
            if not isinstance(e, dict):
                continue
            fields = e.get("fields") or []
            if isinstance(fields, list):
                for f in fields:
                    if not isinstance(f, dict):
                        continue
                    ft = (f.get("field_type") or f.get("ftype") or "str").lower().strip()
                    if ft not in valid_field_types:
                        f["field_type"] = "str"
                    else:
                        f["field_type"] = ft
                    # Ensure field_type key exists
                    if "field_type" not in f:
                        f["field_type"] = ft

    # Sanitize flow step actions
    for c in (data.get("commands") or []):
        if not isinstance(c, dict):
            continue
        steps = c.get("flow_steps") or []
        if isinstance(steps, list):
            for s in steps:
                if not isinstance(s, dict):
                    continue
                act = (s.get("action") or "ask").lower().strip()
                if act not in ("ask", "store", "confirm", "compute", "notify"):
                    s["action"] = "ask"

    # Sanitize buttons — ensure callback_id and target_command are present
    import re as _re
    buttons = data.get("buttons") or []
    if isinstance(buttons, list):
        cmd_names = {(c.get("name") or "").lower().strip() for c in (data.get("commands") or []) if isinstance(c, dict) and c.get("name")}
        for b in buttons:
            if not isinstance(b, dict):
                continue
            # Ensure callback_id exists
            cb = (b.get("callback_id") or "").strip()
            if not cb:
                # Auto-fill from target_command
                tc = (b.get("target_command") or "").strip()
                if tc:
                    cb = tc.lower().replace(" ", "_")
                else:
                    # Auto-fill from label
                    label = (b.get("label") or "").strip()
                    cb = _re.sub(r"[^a-zA-Z0-9\u0600-\u06FF]", "_", label).strip("_").lower() or "btn"
                b["callback_id"] = cb
            # Ensure target_command exists — try to match callback_id to a command
            tc = (b.get("target_command") or "").strip()
            if not tc:
                cb_lower = b["callback_id"].lower()
                if cb_lower in cmd_names:
                    b["target_command"] = cb_lower
                else:
                    # Try matching label to command descriptions
                    pass

    # ── Auto-infer action_type from command name when AI didn't provide it ──
    # This is a safety net: if the AI classified a command as kind=action (or custom
    # for a well-known group-management verb) but didn't set action_type, we infer it
    # from the command name so the transpiler can generate a real Telegram API call.
    _NAME_ACTION_MAP = {
        "ban": "ban_user",
        "unban": "unban_user",
        "mute": "mute_user",
        "unmute": "unmute_user",
        "kick": "kick_user",
        "warn": "warn_user",
        "unwarn": "unwarn_user",
        "warnings": "show_warnings",
        "clearwarnings": "clear_warnings",
        "pin": "pin_message",
        "unpin": "unpin_message",
        "purge": "purge_messages",
        "clean": "clean_messages",
        "delete": "delete_message",
        "slowmode": "set_slowmode",
        "lock": "toggle_setting",
        "unlock": "toggle_setting",
        "locks": "show_locks",
        "welcome": "show_welcome",
        "goodbye": "show_goodbye",
        "setwelcome": "set_welcome",
        "setgoodbye": "set_goodbye",
        "setrules": "set_rules",
        "rules": "show_rules",
        "captcha": "toggle_setting",
        "antilink": "toggle_setting",
        "antispam": "toggle_setting",
        "antiflood": "toggle_setting",
        "antibot": "toggle_setting",
        "filter": "add_filter",
        "unfilter": "remove_filter",
        "filters": "show_filters",
        "blacklist": "add_blacklist",
        "unblacklist": "remove_blacklist",
        "blacklists": "show_blacklist",
        "whitelist": "add_whitelist",
        "unwhitelist": "remove_whitelist",
        "whitelists": "show_whitelist",
        "broadcast": "broadcast_message",
        "stats": "show_stats",
        "groups": "show_groups",
        "users": "show_users",
        "backup": "backup_data",
        "restore": "restore_data",
        "logs": "show_logs",
        "maintenance": "toggle_setting",
        "restart": "restart_bot",
        "panel": "show_panel",
        "admins": "show_admins",
        "staff": "show_staff",
        "id": "show_id",
        "info": "show_info",
        "report": "report_user",
        "language": "set_language",
        "settings": "show_settings",
    }
    for c in (data.get("commands") or []):
        if not isinstance(c, dict):
            continue
        at = (c.get("action_type") or "").strip().lower()
        if not at:
            cname = (c.get("name") or "").strip().lower().lstrip("/")
            if cname in _NAME_ACTION_MAP:
                c["action_type"] = _NAME_ACTION_MAP[cname]
                # Also upgrade kind to action if it was custom and the action is a real verb
                if (c.get("kind") or "custom") == "custom":
                    verb_actions = {
                        "ban_user", "unban_user", "mute_user", "unmute_user",
                        "kick_user", "warn_user", "unwarn_user", "clear_warnings",
                        "pin_message", "unpin_message", "purge_messages",
                        "clean_messages", "delete_message", "set_slowmode",
                        "toggle_setting", "add_filter", "remove_filter",
                        "add_blacklist", "remove_blacklist", "add_whitelist",
                        "remove_whitelist", "broadcast_message", "restart_bot",
                        "report_user",
                    }
                    if c["action_type"] in verb_actions:
                        c["kind"] = "action"

    return data


def rich_spec_from_dict(data: dict[str, Any]) -> RichSpec:
    """Parse a raw LLM JSON dict into a validated RichSpec, applying safe defaults."""
    if not isinstance(data, dict):
        raise ValueError("spec payload is not a dict")
    # Sanitize enum values before validation (AI may produce invalid enums)
    data = _sanitize_enums(data)
    # Ensure minimums so downstream never sees an empty bot
    spec = RichSpec.model_validate(data)
    spec = spec.ensure_minimums()
    return spec
