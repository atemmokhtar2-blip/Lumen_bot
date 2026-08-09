"""
Planning Service — structural ProgramContract completion before Codegen.

NO domain templates (no ecommerce/ticketing command packs).
Derives only from what is already on the contract:
  entities → one list-style command + one service name per entity
  tech.admin_panel → /admin if missing
  tech.file_handling → storage service if missing
  tech.payments → payments service if missing
  always ensure /start /help
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from ...schemas.program_contract import (
    CommandUnit,
    EntityUnit,
    FieldType,
    FieldUnit,
    ProgramContract,
    ServiceUnit,
)


class PlanningReport(BaseModel):
    ok: bool = True
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    readiness_score: float = 1.0
    blocked: bool = False
    block_reasons: list[str] = Field(default_factory=list)
    applied_rules: list[str] = Field(default_factory=list)
    enriched_fields: dict[str, Any] = Field(default_factory=dict)


def _snake(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name.strip()).lower()
    s = re.sub(r"[^a-z0-9_]", "_", s)
    return (s or "item")[:40]


def _enames(c: ProgramContract) -> set[str]:
    return {e.name for e in c.entities}


def _snames(c: ProgramContract) -> set[str]:
    return {s.name for s in c.services}


def _cnames(c: ProgramContract) -> set[str]:
    return {x.name for x in c.commands}


def _ensure_from_entities(c: ProgramContract, decisions: list[str]):
    """Each entity → service only. Commands stay text-grounded (never invent /order /user)."""
    entities = list(c.entities)
    services = list(c.services)
    cmds = list(c.commands)
    snames = _snames(c)

    for ent in entities:
        snake = _snake(ent.name)
        if not snake:
            continue
        if snake not in snames and f"{snake}s" not in snames:
            services.append(ServiceUnit(name=snake, responsibility=f"ops for {ent.name}"))
            decisions.append(f"service_from_entity:{ent.name}->{snake}")
            snames.add(snake)
    # deliberately no command_from_entity — user must list commands in the text

    return entities, services, cmds


def _ensure_tech_hooks(c: ProgramContract, services: list, cmds: list, decisions: list[str]):
    snames = {s.name for s in services}
    cnames = {x.name for x in cmds}

    if c.tech.admin_panel and "admin" not in cnames:
        cmds.append(CommandUnit(name="admin", description="admin", admin_only=True))
        decisions.append("command_from_tech:admin_panel->admin")
        cnames.add("admin")

    if c.tech.file_handling and "storage" not in snames:
        services.append(ServiceUnit(name="storage", responsibility="file storage"))
        decisions.append("service_from_tech:file_handling->storage")
        snames.add("storage")

    if c.tech.payments and "payments" not in snames:
        services.append(ServiceUnit(name="payments", responsibility="payments"))
        decisions.append("service_from_tech:payments->payments")

    if c.tech.async_queue and "task_queue" not in snames:
        services.append(ServiceUnit(name="task_queue", responsibility="async jobs"))
        decisions.append("service_from_tech:async_queue->task_queue")

    return services, cmds


def _ensure_user_entity(c: ProgramContract, entities: list, decisions: list[str]):
    """Do not invent User entity. Entities come from user text only."""
    return entities


def _assess_risks(c: ProgramContract) -> list[str]:
    risks: list[str] = []
    if c.tech.payments and not any(n.lower() in ("order", "payment", "invoice") for n in _enames(c)):
        risks.append("payments_without_payment_entity")
    if c.tech.admin_panel and "admin" not in _cnames(c):
        risks.append("admin_panel_without_admin_command")
    if len(c.commands) < 2:
        risks.append("too_few_commands")
    if not c.entities:
        risks.append("no_entities")
    return risks


def _readiness(c: ProgramContract, risks: list[str]):
    score = 1.0
    blocks: list[str] = []
    if not c.bot_name or len(c.bot_name) < 2:
        blocks.append("invalid_bot_name")
        score -= 0.5
    if "start" not in _cnames(c):
        blocks.append("missing_start_command")
        score -= 0.4
    score = max(0.0, min(1.0, score - 0.05 * min(len(risks), 6)))
    return score, len(blocks) > 0, blocks


class PlanningService:
    def run(self, contract: ProgramContract):
        decisions: list[str] = []
        applied = ["planning:structural_from_entities", "planning:tech_hooks"]

        entities = _ensure_user_entity(contract, list(contract.entities), decisions)
        tmp = contract.model_copy(update={"entities": entities})
        entities, services, cmds = _ensure_from_entities(tmp, decisions)
        services, cmds = _ensure_tech_hooks(contract, services, cmds, decisions)

        if decisions:
            applied.append("planning:enrichment_applied")

        enriched = contract.model_copy(
            update={
                "entities": entities,
                "services": services,
                "commands": cmds,
                "architecture_rules_applied": list(
                    dict.fromkeys(list(contract.architecture_rules_applied) + applied)
                ),
            }
        ).ensure_minimums()

        risks = _assess_risks(enriched)
        score, blocked, block_reasons = _readiness(enriched, risks)
        report = PlanningReport(
            ok=not blocked,
            decisions=decisions,
            risks=risks,
            readiness_score=score,
            blocked=blocked,
            block_reasons=block_reasons,
            applied_rules=applied,
            enriched_fields={
                "entities": [e.name for e in enriched.entities],
                "services": [s.name for s in enriched.services],
                "commands": [c.name for c in enriched.commands],
                "tech": enriched.tech.model_dump(),
            },
        )
        return enriched, report


def plan(contract: ProgramContract):
    return PlanningService().run(contract)
