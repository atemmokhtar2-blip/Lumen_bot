"""
ContractBuilder — convert a RichSpec into an InferenceResult + ProgramContract.

This is the bridge between Understanding (RichSpec) and Codegen.
It replaces the old lossy round-trip (JSON → sectioned text → regex re-parse)
with a direct, lossless mapping from the AI's structured spec to the engine's
internal models.

Zero hardcoded templates:
  - Command kind comes from RichCommand.kind (AI-chosen), never from stem lists.
  - Wizard steps come from RichCommand.flow_steps / collects_fields.
  - Schema columns come from RichEntity.fields (AI-typed), never from _col_type.
  - Store→command mapping comes from RichCommand.entity, never from soft tuples.
"""

from __future__ import annotations

from typing import Any

from ..dsl.ast import (
    ButtonNode,
    CommandNode,
    EntityNode,
    RelationNode,
)
from ..inference.engine import (
    DecisionPlan,
    InferenceResult,
    LoopPlan,
    SchemaPlan,
)
from ..schemas.program_contract import (
    BotKind,
    CommandUnit,
    ButtonUnit,
    EntityUnit,
    FieldUnit,
    FieldType,
    FlowStep,
    FlowUnit,
    HandlerKind,
    HandlerUnit,
    ProgramContract,
    TechFlags,
    validate_contract,
)
from ..schemas.rich_spec import (
    CommandKind,
    PostAction,
    RichCommand,
    RichEntity,
    RichSpec,
)


# ─────────────────────────── helpers ─────────────────────────────────────

def _ident(name: str) -> str:
    """Turn any name into a valid Python identifier."""
    import re
    s = re.sub(r"[^A-Za-z0-9_]", "_", (name or "").strip())
    s = re.sub(r"_+", "_", s).strip("_").lower()
    if not s:
        s = "x"
    if s[0].isdigit():
        s = "_" + s
    return s


def _py_type(field_type: str) -> str:
    """Map RichSpec FieldType to a Python type string."""
    mapping = {
        "str": "str",
        "int": "int",
        "bool": "bool",
        "float": "float",
        "list": "list",
        "dict": "dict",
        "str|none": "str | None",
        "int|none": "int | None",
    }
    return mapping.get((field_type or "str").lower(), "str")


# ─────────────────────────── RichSpec → InferenceResult ───────────────────

def _entity_to_schema(entity: RichEntity) -> SchemaPlan:
    """Convert a RichEntity into a SchemaPlan with AI-typed columns."""
    cols: list[tuple[str, str]] = [("id", "str"), ("user_id", "int")]
    seen = {"id", "user_id"}
    for f in entity.fields:
        fname = _ident(f.name)
        if fname in seen:
            continue
        seen.add(fname)
        ftype = (f.field_type.value if hasattr(f.field_type, "value") else str(f.field_type)).lower()
        cols.append((fname, _py_type(ftype) if ftype in ("int", "bool", "float") else "str"))
    return SchemaPlan(table=_ident(entity.name), columns=cols, primary_key="id")


def _entity_to_node(entity: RichEntity) -> EntityNode:
    """Convert a RichEntity into an EntityNode (for the transpiler's entities list)."""
    attrs = [_ident(f.name) for f in entity.fields]
    attr_types = {}
    for f in entity.fields:
        ftype = (f.field_type.value if hasattr(f.field_type, "value") else str(f.field_type)).lower()
        attr_types[_ident(f.name)] = ftype if ftype in ("int", "bool", "float", "str") else "str"
    return EntityNode(
        name=entity.name,
        attributes=attrs,
        attr_types=attr_types,
    )


def _command_to_node(cmd: RichCommand) -> CommandNode:
    return CommandNode(
        name=cmd.name,
        description=cmd.description,
        admin_only=cmd.admin_only,
    )


def _button_to_node(btn) -> ButtonNode:
    return ButtonNode(
        label=btn.label,
        callback_id=btn.callback_id,
    )


def _build_wizard(cmd: RichCommand, entity: RichEntity | None) -> dict[str, Any]:
    """
    Build a wizard dict from the spec's flow_steps / collects_fields.
    No hardcoded field preference lists — the AI decides what to collect.
    """
    steps: list[dict[str, str]] = []
    # Prefer explicit flow_steps from the spec
    if cmd.flow_steps:
        for fs in cmd.flow_steps:
            steps.append({
                "key": _ident(fs.key),
                "prompt": fs.prompt or f"أدخل {_ident(fs.key)}:",
            })
    elif cmd.collects_fields:
        # Build steps from collects_fields, using entity field prompts if available
        for field_key in cmd.collects_fields:
            prompt = f"أدخل {_ident(field_key)}:"
            if entity:
                for ef in entity.fields:
                    if _ident(ef.name) == _ident(field_key) and ef.prompt:
                        prompt = ef.prompt
                        break
            steps.append({"key": _ident(field_key), "prompt": prompt})
    if not steps:
        return {}
    return {
        "id": cmd.name,
        "command": cmd.name,
        "entity": cmd.entity or "record",
        "kind": cmd.kind.value if hasattr(cmd.kind, "value") else str(cmd.kind),
        "steps": steps,
    }


def _action_name_for(cmd: RichCommand) -> str | None:
    """Derive a logic action name from the command's post_action + entity."""
    kind = cmd.kind.value if hasattr(cmd.kind, "value") else str(cmd.kind)
    if cmd.post_action == PostAction.STORE and cmd.entity:
        return f"create_{_ident(cmd.entity)}"
    if cmd.post_action == PostAction.COMPUTE:
        return f"compute_{cmd.name}"
    if cmd.post_action == PostAction.NOTIFY:
        return f"notify_{cmd.name}"
    if cmd.post_action == PostAction.CONFIRM:
        return f"confirm_{cmd.name}"
    if kind == CommandKind.ACTION.value:
        return f"action_{cmd.name}"
    return None


def build_inference_result(spec: RichSpec) -> InferenceResult:
    """
    Convert a RichSpec into an InferenceResult that the existing transpiler
    can consume — but with all classification decisions coming from the spec.
    """
    # Schemas from entities
    schemas = [_entity_to_schema(e) for e in spec.entities]
    entity_nodes = [_entity_to_node(e) for e in spec.entities]
    entity_by_name = {e.name: e for e in spec.entities}

    # Commands
    cmd_nodes = [_command_to_node(c) for c in spec.commands]
    btn_nodes = [_button_to_node(b) for b in spec.buttons]

    # Wizards — only for collect-kind commands with fields
    wizards: list[dict[str, Any]] = []
    actions: list[str] = []
    compute_steps: list[dict[str, Any]] = []
    for cmd in spec.commands:
        kind = cmd.kind.value if hasattr(cmd.kind, "value") else str(cmd.kind)
        entity = entity_by_name.get(cmd.entity) if cmd.entity else None
        if kind == CommandKind.COLLECT.value:
            wiz = _build_wizard(cmd, entity)
            if wiz:
                wizards.append(wiz)
        aname = _action_name_for(cmd)
        if aname:
            actions.append(aname)
        if cmd.post_action == PostAction.COMPUTE:
            compute_steps.append({
                "name": f"compute_{cmd.name}",
                "label": cmd.description or cmd.name,
            })

    # Decisions from rules (simple: each rule → a decision plan)
    decisions: list[DecisionPlan] = []
    for r in spec.rules:
        decisions.append(DecisionPlan(
            name=_ident(r.name or r.condition[:20] or "rule"),
            discriminant=r.condition,
            branches=[{"effect": r.effect}],
        ))

    # Loops — none from spec unless flows define them; keep empty
    loops: list[LoopPlan] = []

    wants_db = spec.has_database() and bool(spec.entities)
    wants_files = spec.tech.file_handling

    return InferenceResult(
        loops=loops,
        decisions=decisions,
        schemas=schemas,
        actions=actions,
        receives=[],
        emits=[],
        compute_steps=compute_steps,
        wizards=wizards,
        relations=[],
        entities=entity_nodes,
        commands=cmd_nodes,
        buttons=btn_nodes,
        rules=[],
        wants_database=wants_db,
        wants_files=wants_files,
    )


# ─────────────────────────── RichSpec → ProgramContract ───────────────────

_BOT_KIND_MAP = {
    "ecommerce": BotKind.ECOMMERCE,
    "admin": BotKind.ADMIN,
    "community": BotKind.COMMUNITY,
    "ticketing": BotKind.TICKETING,
    "game": BotKind.GAME,
    "assistant": BotKind.ASSISTANT,
    "document": BotKind.DOCUMENT,
    "notification": BotKind.NOTIFICATION,
    "booking": BotKind.BOOKING,
    "utility": BotKind.UTILITY,
    "custom": BotKind.CUSTOM,
}


def _rich_field_to_unit(field) -> FieldUnit:
    ftype_str = (field.field_type.value if hasattr(field.field_type, "value") else str(field.field_type)).lower()
    ftype_map = {
        "str": FieldType.STR,
        "int": FieldType.INT,
        "bool": FieldType.BOOL,
        "float": FieldType.FLOAT,
        "list": FieldType.LIST,
        "dict": FieldType.DICT,
        "str|none": FieldType.OPTIONAL_STR,
        "int|none": FieldType.OPTIONAL_INT,
    }
    return FieldUnit(name=_ident(field.name), field_type=ftype_map.get(ftype_str, FieldType.STR))


def build_contract(spec: RichSpec) -> ProgramContract:
    """
    Convert a RichSpec into a ProgramContract — the formal interface between
    understanding and codegen. This is a direct, lossless mapping.
    """
    commands = [
        CommandUnit(name=c.name, description=c.description, admin_only=c.admin_only)
        for c in spec.commands
    ]
    buttons = [
        ButtonUnit(label=b.label, callback_id=b.callback_id)
        for b in spec.buttons
    ]
    entities = [
        EntityUnit(
            name=e.name,
            fields=[_rich_field_to_unit(f) for f in e.fields],
        )
        for e in spec.entities
    ]
    # Handlers — one per command, plus message + callback
    handlers: list[HandlerUnit] = []
    for c in spec.commands:
        kind = c.kind.value if hasattr(c.kind, "value") else str(c.kind)
        hkind = HandlerKind.CONVERSATION if kind == CommandKind.COLLECT.value else HandlerKind.COMMAND
        handlers.append(HandlerUnit(
            id=f"{c.name}_handler",
            kind=hkind,
            triggers=[c.name],
            admin_only=c.admin_only,
            description=c.description,
        ))
    handlers.append(HandlerUnit(id="message_handler", kind=HandlerKind.MESSAGE, triggers=[]))
    handlers.append(HandlerUnit(id="callback_handler", kind=HandlerKind.CALLBACK, triggers=[]))

    # Flows from spec flows + collect-command wizards
    flows: list[FlowUnit] = []
    for f in spec.flows:
        steps = [
            FlowStep(id=_ident(s.key), action=s.action, label=s.prompt)
            for s in f.steps
        ]
        flows.append(FlowUnit(name=f.name, steps=steps))
    # Also create a flow per collect command
    for cmd in spec.commands:
        kind = cmd.kind.value if hasattr(cmd.kind, "value") else str(cmd.kind)
        if kind == CommandKind.COLLECT.value and cmd.flow_steps:
            steps = [
                FlowStep(id=_ident(s.key), action=s.action, label=s.prompt)
                for s in cmd.flow_steps
            ]
            flows.append(FlowUnit(name=f"flow_{cmd.name}", steps=steps))

    # Conversation states from collect commands
    conversation_states = []
    for cmd in spec.commands:
        kind = cmd.kind.value if hasattr(cmd.kind, "value") else str(cmd.kind)
        if kind == CommandKind.COLLECT.value:
            fields = cmd.collects_fields or [s.key for s in cmd.flow_steps]
            for i, fk in enumerate(fields):
                next_state = f"flow_{cmd.name}:{i+1}" if i + 1 < len(fields) else None
                conversation_states.append({
                    "name": f"flow_{cmd.name}:{i}",
                    "prompt": f"أدخل {_ident(fk)}:",
                    "next_state": next_state,
                    "collects_field": _ident(fk),
                })

    tech = TechFlags(
        database=spec.tech.database,
        payments=spec.tech.payments,
        admin_panel=spec.tech.admin_panel,
        async_queue=spec.tech.async_queue,
        file_handling=spec.tech.file_handling,
        state_management=spec.tech.state_management,
    )

    bot_kind = _BOT_KIND_MAP.get(spec.bot_kind.lower(), BotKind.CUSTOM)

    contract = ProgramContract(
        schema_version="2.0",
        bot_name=spec.bot_name,
        bot_kind=bot_kind,
        summary=spec.description,
        commands=commands,
        buttons=buttons,
        handlers=handlers,
        entities=entities,
        flows=flows,
        tech=tech,
        feature_tags=[],
        hard_constraints=list(spec.hard_constraints),
    )
    return contract.ensure_minimums()


# ─────────────────────────── combined result ─────────────────────────────

class SpecBuildResult:
    """Holds both the InferenceResult and the ProgramContract built from a RichSpec."""

    def __init__(self, inference: InferenceResult, contract: ProgramContract):
        self.inference = inference
        self.contract = contract
        val = validate_contract(contract)
        self.contract_ok = val.ok
        self.contract_errors = list(val.errors)
        self.contract_warnings = list(val.warnings)


def build_from_spec(spec: RichSpec) -> SpecBuildResult:
    """
    Full conversion: RichSpec → (InferenceResult, ProgramContract).
    This is the ONLY bridge between understanding and codegen in the new pipeline.
    """
    inference = build_inference_result(spec)
    contract = build_contract(spec)
    return SpecBuildResult(inference=inference, contract=contract)
