"""
Understanding Service — natural language → ProgramContract only.

Does NOT write project files. Does NOT generate Python sources.
"""

from __future__ import annotations

import re

import hashlib
import re
from typing import Any

from ...schemas.program_contract import (
    BotKind,
    ButtonUnit,
    CommandUnit,
    ContractValidation,
    ConversationStateUnit,
    EntityUnit,
    FieldType,
    FieldUnit,
    FlowStep,
    FlowUnit,
    HandlerKind,
    HandlerUnit,
    PermissionUnit,
    ProgramContract,
    QualityFlags,
    ServiceUnit,
    TechFlags,
    validate_contract,
)
from ...understanding.requirement_extractor import extract_formal_spec
from ...understanding.flow_extractor import extract_flows
from ...schemas.formal_spec import FormalBotSpec


def _cb_id(label: str, raw: str | None = None) -> str:
    seed = (raw or label or "btn").strip()
    ascii_id = re.sub(r"[^a-zA-Z0-9_]", "_", seed)[:40].strip("_")
    if ascii_id and ascii_id.isascii():
        return ascii_id
    return "b_" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]


def _map_kind(bot_type: str, tags: list[str]) -> BotKind:
    if "booking" in tags:
        return BotKind.BOOKING
    mapping = {
        "ecommerce": BotKind.ECOMMERCE,
        "ticketing": BotKind.TICKETING,
        "admin": BotKind.ADMIN,
        "assistant": BotKind.ASSISTANT,
        "document": BotKind.DOCUMENT,
        "notification": BotKind.NOTIFICATION,
        "game": BotKind.GAME,
        "community": BotKind.COMMUNITY,
        "utility": BotKind.UTILITY,
    }
    return mapping.get(bot_type, BotKind.CUSTOM)


def _field_type(hint: str) -> FieldType:
    h = (hint or "str").replace(" ", "")
    table = {
        "str": FieldType.STR,
        "int": FieldType.INT,
        "bool": FieldType.BOOL,
        "float": FieldType.FLOAT,
        "list": FieldType.LIST,
        "dict": FieldType.DICT,
        "str|None": FieldType.OPTIONAL_STR,
        "int|None": FieldType.OPTIONAL_INT,
    }
    if "list" in h:
        return FieldType.LIST
    if "dict" in h:
        return FieldType.DICT
    return table.get(h, FieldType.STR)


def formal_spec_to_contract(spec: FormalBotSpec, raw_text: str = "") -> ProgramContract:
    commands = [
        CommandUnit(
            name=c.command,
            description=c.description or c.command,
            admin_only=bool(c.admin_only),
        )
        for c in (spec.ui.commands or [])
    ]
    buttons = [
        ButtonUnit(label=b.text, callback_id=_cb_id(b.text, b.callback_data))
        for b in (spec.ui.main_buttons or [])
    ]
    handlers = [
        HandlerUnit(
            id=h.name,
            kind=HandlerKind(h.handler_type) if h.handler_type in HandlerKind._value2member_map_ else HandlerKind.COMMAND,
            triggers=list(h.triggers or []),
            admin_only=bool(h.admin_only),
            description=h.description or "",
        )
        for h in (spec.handlers or [])
    ]
    # Ensure handler unit per command
    have = {h.id for h in handlers}
    for c in commands:
        if c.name not in have:
            handlers.append(
                HandlerUnit(
                    id=c.name,
                    kind=HandlerKind.COMMAND,
                    triggers=[f"/{c.name}"],
                    admin_only=c.admin_only,
                    description=c.description,
                )
            )
    entities: list[EntityUnit] = []
    for m in spec.data_models or []:
        fields: list[FieldUnit] = []
        typed = list(getattr(m, "typed_fields", None) or [])
        if typed:
            for f in typed:
                fields.append(FieldUnit(name=f.name, field_type=_field_type(f.type_hint)))
        else:
            for name in m.fields or ["id"]:
                fields.append(FieldUnit(name=name, field_type=FieldType.STR))
        entities.append(EntityUnit(name=m.name, fields=fields))

    services = [
        ServiceUnit(name=s, responsibility=s) for s in (spec.services or [])
    ]

    # Flows primarily from user text steps; tags only fill if text has none
    flows: list[FlowUnit] = []
    for flow_name, step_dicts in extract_flows(raw_text or spec.description or ""):
        # Also try full source if description short
        flows.append(
            FlowUnit(
                name=flow_name,
                steps=[
                    FlowStep(id=s["id"], action=s["action"], next_id=s.get("next_id"), label=str(s.get("label") or "")[:200])
                    for s in step_dicts
                ],
            )
        )
    if not flows:
        # Re-scan using formal spec source sections if present
        joined = "\n".join((spec.source_sections or {}).values()) if getattr(spec, "source_sections", None) else ""
        for flow_name, step_dicts in extract_flows(joined or (spec.description or "")):
            flows.append(
                FlowUnit(
                    name=flow_name,
                    steps=[
                        FlowStep(id=s["id"], action=s["action"], next_id=s.get("next_id"), label=str(s.get("label") or "")[:200])
                        for s in step_dicts
                    ],
                )
            )

    # Permissions: prefer extracted roles from text; else derive from commands
    user_cmds = [c.name for c in commands if not c.admin_only]
    admin_cmds = [c.name for c in commands if c.admin_only]
    permissions: list[PermissionUnit] = []
    for r in (spec.roles or []):
        rname = (r.name or "user").strip().lower()
        # map Arabic role names to role keys without domain packs
        if any(k in rname for k in ("admin", "أدمن", "ادمن", "مشرف", "مدير", "manager")):
            key = "admin"
        else:
            key = re.sub(r"[^a-z0-9_\u0600-\u06ff]+", "_", rname)[:32] or "user"
        allows = list(user_cmds) if key != "admin" else list({*user_cmds, *admin_cmds})
        # permission strings that look like commands
        for perm in (r.permissions or []):
            m = re.search(r"/([a-zA-Z][a-zA-Z0-9_]{1,32})", perm)
            if m and m.group(1) not in allows:
                allows.append(m.group(1))
        permissions.append(PermissionUnit(role=key, allows=allows + [b.callback_id for b in buttons]))
    if not permissions:
        permissions = [
            PermissionUnit(role="user", allows=user_cmds + [b.callback_id for b in buttons]),
            PermissionUnit(role="admin", allows=list({*user_cmds, *admin_cmds, *[b.callback_id for b in buttons]})),
        ]

    # Conversation states from flows
    conversation_states: list[ConversationStateUnit] = []
    for fl in flows:
        for step in fl.steps:
            # prefer human label from flow step when present
            prompt = getattr(step, "label", None) or step.action.replace("_", " ")
            conversation_states.append(
                ConversationStateUnit(
                    name=f"{fl.name}__{step.id}",
                    prompt=str(prompt)[:200],
                    next_state=(f"{fl.name}__{step.next_id}" if step.next_id else None),
                    collects_field=step.id if str(step.action).startswith(("collect", "ask", "pick")) else None,
                )
            )

    kind = _map_kind(spec.bot_type.value, list(spec.feature_tags or []))

    return ProgramContract(
        bot_name=spec.bot_name,
        bot_kind=kind,
        summary=(spec.description or "")[:500],
        commands=commands,
        buttons=buttons,
        handlers=handlers,
        entities=entities,
        services=services,
        flows=flows,
        permissions=permissions,
        conversation_states=conversation_states,
        integrations=list(spec.integrations or ["telegram"]),
        feature_tags=list(spec.feature_tags or []),
        tech=TechFlags(
            database=spec.database.value if spec.database else "sqlite",
            payments=bool(spec.requires_payments),
            admin_panel=bool(spec.requires_admin_panel),
            async_queue=bool(spec.requires_async_queue),
            file_handling=bool(spec.requires_file_handling),
            state_management=bool(spec.requires_state_management),
        ),
        quality=QualityFlags(
            high_performance=bool(spec.quality.high_performance),
            full_error_handling=bool(spec.quality.full_error_handling),
            concurrent_users=bool(spec.quality.concurrent_users),
            modular_code=bool(spec.quality.modular_code),
        ),
        hard_constraints=list(spec.hard_constraints or []),
        architecture_rules_applied=list(spec.architecture_rules_applied or []),
    ).ensure_minimums()


class UnderstandingService:
    """Microservice: text → ProgramContract."""

    def run(self, user_text: str) -> tuple[ProgramContract, ContractValidation]:
        spec = extract_formal_spec(user_text or "")
        contract = formal_spec_to_contract(spec, raw_text=user_text or "")
        validation = validate_contract(contract)
        return contract, validation


def understand(user_text: str) -> tuple[ProgramContract, ContractValidation]:
    return UnderstandingService().run(user_text)
