"""
Understanding Service — natural language → ProgramContract only.

Does NOT write project files. Does NOT generate Python sources.
"""

from __future__ import annotations

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


def formal_spec_to_contract(spec: FormalBotSpec) -> ProgramContract:
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

    # Optional simple flow from feature tags
    flows: list[FlowUnit] = []
    if "shopping_cart" in (spec.feature_tags or []) or "order_management" in (spec.feature_tags or []):
        flows.append(
            FlowUnit(
                name="checkout",
                steps=[
                    FlowStep(id="browse", action="list_products", next_id="cart"),
                    FlowStep(id="cart", action="view_cart", next_id="checkout"),
                    FlowStep(id="checkout", action="create_order", next_id=None),
                ],
            )
        )
    if "booking" in (spec.feature_tags or []):
        flows.append(
            FlowUnit(
                name="booking",
                steps=[
                    FlowStep(id="pick", action="pick_slot", next_id="confirm"),
                    FlowStep(id="confirm", action="confirm_booking", next_id=None),
                ],
            )
        )

    # Permissions derived from commands (not templates — from contract inputs)
    user_cmds = [c.name for c in commands if not c.admin_only]
    admin_cmds = [c.name for c in commands if c.admin_only]
    permissions = [
        PermissionUnit(role="user", allows=user_cmds + [b.callback_id for b in buttons]),
        PermissionUnit(role="admin", allows=list({*user_cmds, *admin_cmds, *[b.callback_id for b in buttons]})),
    ]

    # Conversation states from flows
    conversation_states: list[ConversationStateUnit] = []
    for fl in flows:
        for step in fl.steps:
            conversation_states.append(
                ConversationStateUnit(
                    name=f"{fl.name}__{step.id}",
                    prompt=step.action.replace("_", " "),
                    next_state=(f"{fl.name}__{step.next_id}" if step.next_id else None),
                    collects_field=step.id if step.action.startswith(("collect", "ask", "pick")) else None,
                )
            )

    # Booking kind boost entities if missing
    kind = _map_kind(spec.bot_type.value, list(spec.feature_tags or []))
    entity_names = {e.name for e in entities}
    if kind == BotKind.BOOKING and "Appointment" not in entity_names:
        entities.append(
            EntityUnit(
                name="Appointment",
                fields=[
                    FieldUnit(name="id", field_type=FieldType.STR),
                    FieldUnit(name="user_id", field_type=FieldType.INT),
                    FieldUnit(name="slot", field_type=FieldType.STR),
                    FieldUnit(name="status", field_type=FieldType.STR),
                ],
            )
        )
        if not any(s.name == "booking" for s in services):
            services.append(ServiceUnit(name="booking", responsibility="appointments"))

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
        contract = formal_spec_to_contract(spec)
        validation = validate_contract(contract)
        return contract, validation


def understand(user_text: str) -> tuple[ProgramContract, ContractValidation]:
    return UnderstandingService().run(user_text)
