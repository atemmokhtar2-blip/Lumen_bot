"""
Intent Parser Engine — powered by Formal Understanding.

Produces the exact ``intent`` dict shape expected by ParseStage and
BlueprintComposerEngine.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..base.base_engine import BaseEngine


def _build_intent_from_spec(spec: Any, raw_request: str) -> Dict[str, Any]:
    """Map FormalBotSpec → legacy intent dict used by the pipeline."""
    bot_type = getattr(spec.bot_type, "value", str(spec.bot_type))
    # Map formal types to profile keys the composer understands
    type_map = {
        "ecommerce": "store",
        "ticketing": "general",
        "admin": "group_admin",
        "community": "group_admin",
        "game": "general",
        "assistant": "general",
        "document": "general",
        "notification": "general",
        "utility": "general",
        "custom": "general",
    }
    mapped_type = type_map.get(bot_type, bot_type if bot_type in (
        "store", "group_admin", "company_ops", "task_manager", "general"
    ) else "general")

    features: List[str] = []
    for f in getattr(spec, "features", []) or []:
        name = getattr(f, "name", None) or (f.get("name") if isinstance(f, dict) else str(f))
        if name:
            features.append(str(name)[:80])

    # Capabilities as extra feature signals
    for cap in getattr(spec, "capabilities", []) or []:
        if cap and cap not in features:
            features.append(str(cap))

    commands: List[Dict[str, Any]] = []
    ui = getattr(spec, "ui", None)
    if ui is not None:
        for cmd in getattr(ui, "commands", []) or []:
            commands.append({
                "name": getattr(cmd, "command", "start"),
                "description": getattr(cmd, "description", ""),
                "admin_only": bool(getattr(cmd, "admin_only", False)),
            })
    if not commands:
        commands = [
            {"name": "start", "description": "تشغيل البوت"},
            {"name": "help", "description": "المساعدة"},
        ]

    # Domain command hints from flags
    if getattr(spec, "requires_payments", False) and not any(c["name"] == "pay" for c in commands):
        commands.append({"name": "cart", "description": "السلة"})
        commands.append({"name": "checkout", "description": "إتمام الشراء"})
    if getattr(spec, "requires_admin_panel", False) and not any(c["name"] == "admin" for c in commands):
        commands.append({"name": "admin", "description": "لوحة الإدارة", "admin_only": True})

    intent: Dict[str, Any] = {
        "raw": raw_request.strip() or getattr(spec, "description", "telegram bot"),
        "bot_type": mapped_type,
        "bot_name": getattr(spec, "bot_name", "TelegramBot"),
        "features": features[:40],
        "commands": commands,
        "language": "python",
        "language_version": "3.11",
        "framework": "python-telegram-bot",
        "database": getattr(getattr(spec, "database", None), "value", "sqlite"),
        "requires_payments": bool(getattr(spec, "requires_payments", False)),
        "requires_admin_panel": bool(getattr(spec, "requires_admin_panel", False)),
        "requires_async_queue": bool(getattr(spec, "requires_async_queue", False)),
        "requires_file_handling": bool(getattr(spec, "requires_file_handling", False)),
        "languages": [getattr(l, "value", str(l)) for l in (getattr(spec, "languages", None) or [])],
        "source": "formal_understanding",
    }
    return intent


class IntentParserEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(
            name="intent_parser",
            version="2.1.0",
            description="Formal understanding → pipeline intent artefact",
            tags=["understanding", "formal"],
        )

    def execute(self, context):
        request = (getattr(context, "request", None) or "").strip()

        # Reuse existing formal spec if present
        spec = context.artefacts.get("formal_bot_spec") if hasattr(context, "artefacts") else None

        if spec is None:
            try:
                from .formal_understanding.formal_understanding_engine import FormalUnderstandingEngine
                result = FormalUnderstandingEngine().execute(context)
                if not result.success:
                    return result
                spec = context.artefacts.get("formal_bot_spec")
            except Exception as exc:
                return self.failed([f"Formal understanding failed: {exc}"])

        if spec is None:
            return self.failed(["Formal understanding did not produce formal_bot_spec"])

        intent = _build_intent_from_spec(spec, request or getattr(spec, "description", ""))

        # Write both legacy and formal artefacts
        context.artefacts["intent"] = intent
        try:
            context.set("intent", intent)
        except Exception:
            pass

        return self.ok(
            outputs={"intent": intent},
            metadata={"engine": "intent_parser", "source": "formal_understanding"},
        )
