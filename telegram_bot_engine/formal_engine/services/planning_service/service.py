"""
Planning Service — ProgramContract enrichment before Codegen.
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from ...schemas.program_contract import (
    BotKind, CommandUnit, EntityUnit, FieldType, FieldUnit,
    ProgramContract, ServiceUnit, TechFlags,
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

_DOMAIN_ENTITIES: dict[BotKind, list[tuple[str, list[tuple[str, FieldType]]]]] = {
    BotKind.ECOMMERCE: [
        ("Product", [("id", FieldType.STR), ("name", FieldType.STR), ("price", FieldType.FLOAT), ("description", FieldType.STR), ("stock", FieldType.INT)]),
        ("CartItem", [("user_id", FieldType.INT), ("product_id", FieldType.STR), ("qty", FieldType.INT)]),
        ("Order", [("id", FieldType.STR), ("user_id", FieldType.INT), ("total", FieldType.FLOAT), ("status", FieldType.STR), ("address", FieldType.OPTIONAL_STR)]),
        ("User", [("id", FieldType.INT), ("telegram_id", FieldType.INT), ("name", FieldType.STR), ("phone", FieldType.OPTIONAL_STR)]),
    ],
    BotKind.TICKETING: [
        ("Ticket", [("id", FieldType.STR), ("user_id", FieldType.INT), ("subject", FieldType.STR), ("body", FieldType.STR), ("status", FieldType.STR), ("priority", FieldType.STR)]),
        ("TicketMessage", [("id", FieldType.STR), ("ticket_id", FieldType.STR), ("sender_id", FieldType.INT), ("text", FieldType.STR)]),
    ],
    BotKind.BOOKING: [
        ("Appointment", [("id", FieldType.STR), ("user_id", FieldType.INT), ("slot", FieldType.STR), ("status", FieldType.STR)]),
        ("User", [("id", FieldType.INT), ("telegram_id", FieldType.INT), ("name", FieldType.STR)]),
    ],
    BotKind.ADMIN: [
        ("AdminAction", [("id", FieldType.STR), ("admin_id", FieldType.INT), ("action", FieldType.STR), ("target", FieldType.STR)]),
    ],
    BotKind.COMMUNITY: [
        ("Member", [("id", FieldType.INT), ("telegram_id", FieldType.INT), ("role", FieldType.STR), ("joined_at", FieldType.STR)]),
        ("Post", [("id", FieldType.STR), ("author_id", FieldType.INT), ("text", FieldType.STR), ("status", FieldType.STR)]),
    ],
}
_DOMAIN_SERVICES: dict[BotKind, list[tuple[str, str]]] = {
    BotKind.ECOMMERCE: [("catalog", "product listing"), ("cart", "cart ops"), ("orders", "order lifecycle")],
    BotKind.TICKETING: [("tickets", "ticket ops"), ("assignment", "admin assignment")],
    BotKind.BOOKING: [("booking", "scheduling"), ("slots", "time slots")],
    BotKind.ADMIN: [("admin", "admin panel")],
    BotKind.COMMUNITY: [("members", "member mgmt"), ("moderation", "moderation")],
}
_DOMAIN_COMMANDS: dict[BotKind, list[tuple[str, str, bool]]] = {
    BotKind.ECOMMERCE: [("products", "عرض المنتجات", False), ("cart", "السلة", False), ("orders", "طلباتي", False), ("admin", "لوحة الإدارة", True)],
    BotKind.TICKETING: [("new", "فتح تذكرة", False), ("mytickets", "تذاكري", False), ("admin", "إدارة التذاكر", True)],
    BotKind.BOOKING: [("book", "حجز موعد", False), ("mybookings", "حجوزاتي", False), ("admin", "إدارة الحجوزات", True)],
    BotKind.ADMIN: [("admin", "لوحة الإدارة", True), ("stats", "إحصائيات", True)],
    BotKind.COMMUNITY: [("members", "الأعضاء", False), ("admin", "الإشراف", True)],
}

def _enames(c): return {e.name for e in c.entities}
def _snames(c): return {s.name for s in c.services}
def _cnames(c): return {x.name for x in c.commands}

def _ensure_entities(c, decisions):
    entities, names = list(c.entities), _enames(c)
    for name, fields in _DOMAIN_ENTITIES.get(c.bot_kind, []):
        if name not in names:
            entities.append(EntityUnit(name=name, fields=[FieldUnit(name=fn, field_type=ft) for fn, ft in fields]))
            decisions.append(f"added_entity:{name}"); names.add(name)
    if c.tech.payments:
        if "Order" not in names:
            entities.append(EntityUnit(name="Order", fields=[FieldUnit(name="id", field_type=FieldType.STR), FieldUnit(name="user_id", field_type=FieldType.INT), FieldUnit(name="total", field_type=FieldType.FLOAT), FieldUnit(name="status", field_type=FieldType.STR)]))
            decisions.append("added_entity:Order"); names.add("Order")
        if "Payment" not in names:
            entities.append(EntityUnit(name="Payment", fields=[FieldUnit(name="id", field_type=FieldType.STR), FieldUnit(name="order_id", field_type=FieldType.STR), FieldUnit(name="amount", field_type=FieldType.FLOAT), FieldUnit(name="status", field_type=FieldType.STR)]))
            decisions.append("added_entity:Payment")
    return entities

def _ensure_services(c, decisions):
    services, names = list(c.services), _snames(c)
    for name, resp in _DOMAIN_SERVICES.get(c.bot_kind, []):
        if name not in names:
            services.append(ServiceUnit(name=name, responsibility=resp)); decisions.append(f"added_service:{name}"); names.add(name)
    if c.tech.payments and "payments" not in names:
        services.append(ServiceUnit(name="payments", responsibility="payment processing")); decisions.append("added_service:payments")
    if c.tech.async_queue and "task_queue" not in names:
        services.append(ServiceUnit(name="task_queue", responsibility="async jobs")); decisions.append("added_service:task_queue")
    return services

def _ensure_commands(c, decisions):
    cmds, names = list(c.commands), _cnames(c)
    for name, desc, admin in _DOMAIN_COMMANDS.get(c.bot_kind, []):
        if name not in names:
            cmds.append(CommandUnit(name=name, description=desc, admin_only=admin)); decisions.append(f"added_command:{name}"); names.add(name)
    if c.tech.admin_panel and "admin" not in names:
        cmds.append(CommandUnit(name="admin", description="لوحة الإدارة", admin_only=True)); decisions.append("added_command:admin")
    return cmds

def _refine_tech(c, decisions):
    tech, updates = c.tech, {}
    if c.bot_kind == BotKind.ECOMMERCE or tech.payments:
        if "postgres" in (c.integrations or []):
            updates["database"] = "postgres"; decisions.append("tech:database=postgres")
        if not tech.admin_panel:
            updates["admin_panel"] = True; decisions.append("tech:admin_panel=True")
    if c.bot_kind in (BotKind.ECOMMERCE, BotKind.TICKETING, BotKind.BOOKING) and not tech.state_management:
        updates["state_management"] = True; decisions.append("tech:state_management=True")
    if c.quality.concurrent_users and not tech.async_queue:
        updates["async_queue"] = True; decisions.append("tech:async_queue=True")
    return tech if not updates else tech.model_copy(update=updates)

def _assess_risks(c):
    risks = []
    if c.tech.payments and "Order" not in _enames(c): risks.append("payments_without_order_entity")
    if c.tech.admin_panel and "admin" not in _cnames(c): risks.append("admin_panel_without_admin_command")
    if not c.buttons and c.bot_kind != BotKind.UTILITY: risks.append("no_buttons_weak_ui")
    if c.tech.async_queue and "redis" not in (c.integrations or []): risks.append("async_queue_without_redis")
    if len(c.commands) < 2: risks.append("too_few_commands")
    return risks

def _readiness(c, risks):
    score, blocks = 1.0, []
    if not c.bot_name or len(c.bot_name) < 2: blocks.append("invalid_bot_name"); score -= 0.5
    if "start" not in _cnames(c): blocks.append("missing_start_command"); score -= 0.4
    score = max(0.0, min(1.0, score - 0.05 * min(len(risks), 6)))
    return score, len(blocks) > 0, blocks

class PlanningService:
    def run(self, contract: ProgramContract):
        decisions, applied = [], []
        entities = _ensure_entities(contract, decisions)
        services = _ensure_services(contract, decisions)
        commands = _ensure_commands(contract, decisions)
        tech = _refine_tech(contract, decisions)
        applied += ["planning:domain_completeness", "planning:tech_refinement"]
        if decisions: applied.append("planning:enrichment_applied")
        enriched = contract.model_copy(update={
            "entities": entities, "services": services, "commands": commands, "tech": tech,
            "architecture_rules_applied": list(dict.fromkeys(list(contract.architecture_rules_applied) + applied)),
        }).ensure_minimums()
        risks = _assess_risks(enriched)
        score, blocked, block_reasons = _readiness(enriched, risks)
        report = PlanningReport(
            ok=not blocked, decisions=decisions, risks=risks, readiness_score=round(score, 3),
            blocked=blocked, block_reasons=block_reasons, applied_rules=applied,
            enriched_fields={"entities": [e.name for e in enriched.entities], "services": [s.name for s in enriched.services], "commands": [c.name for c in enriched.commands], "tech": enriched.tech.model_dump()},
        )
        return enriched, report

def plan(contract: ProgramContract):
    return PlanningService().run(contract)
