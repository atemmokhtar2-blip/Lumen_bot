"""SPEC_SCHEMA_V1 — deterministic bot specification (no AI).

This is the single source of truth for zero-AI generation.
Human (or a future builder UI) produces this structure; engines consume it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal


TriggerType = Literal["command", "callback", "message"]
ActorType = Literal["user", "admin", "owner", "any"]
StorageType = Literal["none", "sqlite"]


@dataclass
class Trigger:
    type: TriggerType
    id: str  # command name without slash, or callback_data id


@dataclass
class Action:
    service: str
    method: str


@dataclass
class Messages:
    success: str = ""
    failure: str = ""
    prompt: str = ""


@dataclass
class InputField:
    name: str
    from_: str = "arg"  # arg | reply | user_data | text
    required: bool = True
    enum: list[str] = field(default_factory=list)


@dataclass
class Feature:
    """One executable capability instance in the bot."""
    id: str
    feature: str  # registry key, e.g. user_ban
    actor: ActorType = "user"
    target: str = ""
    trigger: Trigger = field(default_factory=lambda: Trigger("command", "start"))
    permissions: list[str] = field(default_factory=list)
    action: Action = field(default_factory=lambda: Action("core", "noop"))
    inputs: list[InputField] = field(default_factory=list)
    success: dict[str, str] = field(default_factory=dict)
    failure: dict[str, str] = field(default_factory=dict)
    messages: Messages = field(default_factory=Messages)


@dataclass
class EntityField:
    name: str
    type: str = "str"  # str|int|bool|float


@dataclass
class Entity:
    name: str
    fields: list[EntityField] = field(default_factory=list)


@dataclass
class StartButton:
    label: str
    callback_id: str


@dataclass
class BotMeta:
    name: str = "custom_bot"
    language: str = "ar"
    description: str = ""


@dataclass
class StorageSpec:
    type: StorageType = "none"
    entities: list[str] = field(default_factory=list)


@dataclass
class AcceptanceTest:
    """Manual/automated checklist item for a generated bot vertical."""
    name: str
    steps: list[str] = field(default_factory=list)
    expected: str = ""



@dataclass
class UxCopy:
    """User-described copy from translator / fidelity repair."""
    welcome: str = ""
    menu_title: str = ""
    menu_buttons: list[dict[str, str]] = field(default_factory=list)
    contact_phone: str = ""
    contact_text: str = ""
    order_statuses: list[str] = field(default_factory=list)
    order_form_fields: list[str] = field(default_factory=list)
    order_summary_template: str = ""
    confirm_success: str = ""
    cancel_text: str = ""
    back_to_menu: str = ""
    extras: dict[str, str] = field(default_factory=dict)


def _parse_ux(raw) -> "UxCopy":
    if not isinstance(raw, dict):
        return UxCopy()
    buttons = []
    for b in (raw.get("menu_buttons") or [])[:20]:
        if isinstance(b, dict) and str(b.get("label") or "").strip():
            buttons.append({str(k): str(v) for k, v in b.items()})
    return UxCopy(
        welcome=str(raw.get("welcome") or "")[:2000],
        menu_title=str(raw.get("menu_title") or "")[:200],
        menu_buttons=buttons,
        contact_phone=str(raw.get("contact_phone") or "")[:40],
        contact_text=str(raw.get("contact_text") or "")[:500],
        order_statuses=[str(x)[:80] for x in (raw.get("order_statuses") or []) if str(x).strip()][:12],
        order_form_fields=[str(x)[:80] for x in (raw.get("order_form_fields") or []) if str(x).strip()][:12],
        order_summary_template=str(raw.get("order_summary_template") or "")[:1000],
        confirm_success=str(raw.get("confirm_success") or "")[:1000],
        cancel_text=str(raw.get("cancel_text") or "")[:300],
        back_to_menu=str(raw.get("back_to_menu") or "")[:80],
        extras={str(k): str(v)[:500] for k, v in (raw.get("extras") or {}).items()} if isinstance(raw.get("extras"), dict) else {},
    )


@dataclass
class BotSpec:
    """Root specification document — SPEC_SCHEMA_V1."""
    version: str = "1.0"
    bot: BotMeta = field(default_factory=BotMeta)
    actors: list[str] = field(default_factory=lambda: ["user", "admin"])
    entities: list[Entity] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)
    storage: StorageSpec = field(default_factory=StorageSpec)
    start_buttons: list[StartButton] = field(default_factory=list)
    hard_constraints: list[str] = field(default_factory=list)
    # Market-ready extras: QA checklist + demo rows so /start is not empty
    acceptance_tests: list[AcceptanceTest] = field(default_factory=list)
    seed_data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    ux: UxCopy = field(default_factory=UxCopy)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "BotSpec":
        bot_raw = data.get("bot") or {}
        bot = BotMeta(
            name=str(bot_raw.get("name") or "custom_bot"),
            language=str(bot_raw.get("language") or "ar"),
            description=str(bot_raw.get("description") or ""),
        )
        entities: list[Entity] = []
        for e in data.get("entities") or []:
            if not isinstance(e, dict):
                continue
            fields = [
                EntityField(name=str(f.get("name")), type=str(f.get("type") or "str"))
                for f in (e.get("fields") or [])
                if isinstance(f, dict) and f.get("name")
            ]
            if e.get("name"):
                entities.append(Entity(name=str(e["name"]), fields=fields))

        features: list[Feature] = []
        for fr in data.get("features") or []:
            if not isinstance(fr, dict) or not fr.get("feature"):
                continue
            tr = fr.get("trigger") or {}
            act = fr.get("action") or {}
            msgs = fr.get("messages") or {}
            inputs = []
            for inp in fr.get("inputs") or []:
                if not isinstance(inp, dict) or not inp.get("name"):
                    continue
                inputs.append(
                    InputField(
                        name=str(inp["name"]),
                        from_=str(inp.get("from") or inp.get("from_") or "arg"),
                        required=bool(inp.get("required", True)),
                        enum=[str(x) for x in (inp.get("enum") or [])],
                    )
                )
            features.append(
                Feature(
                    id=str(fr.get("id") or fr.get("feature")),
                    feature=str(fr["feature"]),
                    actor=str(fr.get("actor") or "user"),  # type: ignore[arg-type]
                    target=str(fr.get("target") or ""),
                    trigger=Trigger(
                        type=str(tr.get("type") or "command"),  # type: ignore[arg-type]
                        id=str(tr.get("id") or fr.get("feature")),
                    ),
                    permissions=[str(x) for x in (fr.get("permissions") or [])],
                    action=Action(
                        service=str(act.get("service") or "core"),
                        method=str(act.get("method") or "noop"),
                    ),
                    inputs=inputs,
                    success=dict(fr.get("success") or {}) if isinstance(fr.get("success"), dict) else {},
                    failure=dict(fr.get("failure") or {}) if isinstance(fr.get("failure"), dict) else {},
                    messages=Messages(
                        success=str(msgs.get("success") or (fr.get("success") or {}).get("message") or ""),
                        failure=str(msgs.get("failure") or (fr.get("failure") or {}).get("message") or ""),
                        prompt=str(msgs.get("prompt") or ""),
                    ),
                )
            )

        buttons = [
            StartButton(label=str(b.get("label")), callback_id=str(b.get("callback_id")))
            for b in (data.get("start_buttons") or [])
            if isinstance(b, dict) and b.get("label") and b.get("callback_id")
        ]
        st = data.get("storage") or {}
        storage = StorageSpec(
            type=str(st.get("type") or "none"),  # type: ignore[arg-type]
            entities=[str(x) for x in (st.get("entities") or [])],
        )
        acceptance: list[AcceptanceTest] = []
        for at in data.get("acceptance_tests") or []:
            if not isinstance(at, dict) or not at.get("name"):
                continue
            acceptance.append(
                AcceptanceTest(
                    name=str(at["name"]),
                    steps=[str(x) for x in (at.get("steps") or [])],
                    expected=str(at.get("expected") or ""),
                )
            )
        seed_raw = data.get("seed_data") or {}
        seed: dict[str, list[dict[str, Any]]] = {}
        if isinstance(seed_raw, dict):
            for k, rows in seed_raw.items():
                if isinstance(rows, list):
                    seed[str(k)] = [dict(r) for r in rows if isinstance(r, dict)]

        return BotSpec(
            version=str(data.get("version") or "1.0"),
            bot=bot,
            actors=[str(a) for a in (data.get("actors") or ["user", "admin"])],
            entities=entities,
            features=features,
            storage=storage,
            start_buttons=buttons,
            hard_constraints=[str(x) for x in (data.get("hard_constraints") or [])],
            acceptance_tests=acceptance,
            seed_data=seed,
            ux=_parse_ux(data.get("ux")),
        )


__all__ = [
    "BotSpec",
    "BotMeta",
    "Feature",
    "Trigger",
    "Action",
    "Messages",
    "InputField",
    "Entity",
    "EntityField",
    "StartButton",
    "StorageSpec",
    "AcceptanceTest",
]


# ---------------------------------------------------------------------------
# Infinite engine surface (Atomic DAG) — re-exported for callers that import
# from schema.py as documented in the architecture plan.
# Implementation lives in spec_core.infinite (Pydantic V2 DynamicBotSpec).
# ---------------------------------------------------------------------------
try:
    from .infinite.infinite_schema import (  # noqa: E402
        ActionAtom as InfiniteAction,
        ConditionAtom as InfiniteCondition,
        DynamicBotSpec,
        FlowNode,
        TriggerAtom as InfiniteTrigger,
        TransformerAtom as InfiniteTransformer,
    )
    from .infinite.ast_validator import validate_dynamic_spec, SpecValidationError
    from .infinite.jit_compiler import compile_dynamic_spec, render_handlers_python
except Exception:  # pragma: no cover
    DynamicBotSpec = None  # type: ignore
    FlowNode = None  # type: ignore
    InfiniteTrigger = None  # type: ignore
    InfiniteCondition = None  # type: ignore
    InfiniteAction = None  # type: ignore
    InfiniteTransformer = None  # type: ignore
    validate_dynamic_spec = None  # type: ignore
    SpecValidationError = None  # type: ignore
    compile_dynamic_spec = None  # type: ignore
    render_handlers_python = None  # type: ignore
