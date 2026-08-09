"""
Architecture Rules Engine — formal constraints for correct bot design.

Every rule is deterministic. Understanding applies them; generation must obey.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ArchRule:
    id: str
    description: str
    # condition(spec_dict) -> bool
    when: str
    # effects to apply on understanding result
    effects: tuple[str, ...]
    severity: str = "hard"  # hard | soft


# Declarative rules (evaluated in order)
RULES: list[ArchRule] = [
    # Structural minima only — NO domain packs (shop/ticket/edu/ecommerce).
    ArchRule(
        id="R01_START_HELP",
        description="Every bot may expose /start and /help as infrastructure",
        when="always",
        effects=("ensure_command:start", "ensure_command:help"),
    ),
    ArchRule(
        id="R02_BUTTONS_NEED_CALLBACKS",
        description="Every main button must map to a callback trigger",
        when="has_buttons",
        effects=("ensure_callback_handlers_for_buttons",),
    ),
    ArchRule(
        id="R03_ADMIN_GUARD",
        description="If user requested admin panel, ensure /admin exists only when evidenced",
        when="requires_admin_panel",
        effects=("ensure_command:admin", "ensure_config:admin_user_ids"),
    ),
    ArchRule(
        id="R04_FILES_NEED_STORAGE",
        description="File handling implies storage service",
        when="requires_file_handling",
        effects=("ensure_service:storage",),
    ),
    ArchRule(
        id="R05_POSTGRES_SIGNAL",
        description="Explicit postgres request forces postgres database",
        when="mentions_postgres",
        effects=("set_database:postgres", "ensure_integration:postgres"),
    ),
    ArchRule(
        id="R06_CLEAN_LAYERS",
        description="Code must separate handlers / services / models / config",
        when="always",
        effects=("enforce_layering",),
        severity="soft",
    ),
    ArchRule(
        id="R07_TYPED_CONFIG",
        description="Configuration must be typed and env-driven",
        when="always",
        effects=("enforce_typed_config",),
        severity="soft",
    ),
]



def rule_applies(rule: ArchRule, ctx: dict[str, Any]) -> bool:
    w = rule.when
    if w == "always":
        return True
    if w == "has_buttons":
        return bool(ctx.get("buttons"))
    if w == "requires_payments":
        return bool(ctx.get("requires_payments"))
    if w == "requires_admin_panel":
        return bool(ctx.get("requires_admin_panel"))
    if w == "requires_async_queue":
        return bool(ctx.get("requires_async_queue"))
    if w == "requires_file_handling":
        return bool(ctx.get("requires_file_handling"))
    if w == "mentions_postgres":
        return bool(ctx.get("mentions_postgres"))
    if w.startswith("type:"):
        return ctx.get("bot_type") == w.split(":", 1)[1]
    if w.startswith("feature:"):
        return w.split(":", 1)[1] in (ctx.get("feature_tags") or [])
    return False


def apply_architecture_rules(ctx: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """
    Mutates a working context dict with rule effects.
    Returns (updated_ctx, list of applied rule ids).
    """
    applied: list[str] = []
    commands: dict[str, tuple[str, bool]] = {
        c["command"]: (c.get("description") or c["command"], bool(c.get("admin_only")))
        for c in ctx.get("commands") or []
    }
    services: set[str] = set(ctx.get("services") or [])
    models: set[str] = set(ctx.get("model_names") or [])
    integrations: set[str] = set(ctx.get("integrations") or [])
    handlers: set[str] = set(ctx.get("handler_names") or [])
    feature_tags: set[str] = set(ctx.get("feature_tags") or [])

    for rule in RULES:
        if not rule_applies(rule, ctx):
            continue
        applied.append(rule.id)
        for effect in rule.effects:
            if effect.startswith("ensure_command:"):
                cmd = effect.split(":", 1)[1]
                # structural only — never inject domain command packs
                # No fixed command injection (start/help/admin packs removed)
                pass
            elif effect.startswith("ensure_service:"):
                svc = effect.split(":", 1)[1]
                # tech hooks only
                if svc in ("storage", "task_queue", "payments") or svc in services:
                    services.add(svc)
            elif effect.startswith("ensure_model:"):
                # models come from text signals only — skip library injection
                pass
            elif effect.startswith("ensure_integration:"):
                integrations.add(effect.split(":", 1)[1])
            elif effect.startswith("ensure_handler:"):
                handlers.add(effect.split(":", 1)[1])
            elif effect.startswith("ensure_feature:"):
                feature_tags.add(effect.split(":", 1)[1])
            elif effect == "ensure_database":
                # no default database technology injection
                pass
            elif effect.startswith("set_database:"):
                ctx["database"] = effect.split(":", 1)[1]
            elif effect == "ensure_state_management":
                ctx["requires_state_management"] = True
            elif effect == "ensure_config:admin_user_ids":
                ctx["needs_admin_config"] = True
            elif effect == "ensure_callback_handlers_for_buttons":
                for b in ctx.get("buttons") or []:
                    handlers.add(f"cb_{b.get('callback_data', 'btn')}")
            elif effect == "ensure_handlers_for_all_commands":
                for cmd in commands:
                    handlers.add(cmd)
            elif effect.startswith("ensure_language:"):
                langs = list(ctx.get("languages") or [])
                lang = effect.split(":", 1)[1]
                if lang not in langs:
                    langs.append(lang)
                ctx["languages"] = langs

    ctx["commands"] = [
        {"command": k, "description": v[0], "admin_only": v[1]} for k, v in commands.items()
    ]
    ctx["services"] = sorted(services)
    ctx["model_names"] = sorted(models)
    ctx["integrations"] = sorted(integrations)
    ctx["handler_names"] = sorted(handlers)
    ctx["feature_tags"] = sorted(feature_tags)
    return ctx, applied
