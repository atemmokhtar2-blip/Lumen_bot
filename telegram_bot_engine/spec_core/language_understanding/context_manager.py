"""Stage-1/2 unified context manager — short + long + brief memory."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .entities import ExtractedEntities, extract_entities
from .bot_spec_extract import BotBrief, extract_bot_brief
from .learning_layer import MemorySnapshot, recall, apply_full_memory, record_turn_learning
from .memory_engine import MemoryEngine, get_memory_engine
from .engine import understand, LanguageUnderstandingResult
from .intent_analysis import analyze_intent, IntentAnalysis


@dataclass
class TurnContext:
    request: str
    lu: LanguageUnderstandingResult | None = None
    intent: IntentAnalysis | None = None
    entities: ExtractedEntities | None = None
    brief: BotBrief | None = None
    memory: MemorySnapshot | None = None
    enriched_request: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request[:200],
            "enriched_request": self.enriched_request[:300],
            "bot_name": getattr(self.entities, "bot_name", None) if self.entities else None,
            "strict": bool(getattr(self.entities, "strict_spec", False)) if self.entities else False,
            "menu": list(getattr(self.entities, "menu_ids", None) or [])[:12] if self.entities else [],
            "features": list(getattr(self.entities, "features_requested", None) or [])[:20] if self.entities else [],
            "intent": self.intent.primary.intent if self.intent and self.intent.primary else None,
            "memory": self.memory.to_dict() if self.memory else None,
            "notes": self.notes[:8],
        }


def build_turn_context(
    request: str,
    *,
    user_id: int | None = None,
    memory: MemoryEngine | None = None,
) -> TurnContext:
    """Single entry: understand + brief + memory apply for one user turn."""
    raw = request or ""
    ctx = TurnContext(request=raw)
    ctx.lu = understand(raw)
    ctx.intent = analyze_intent(raw, lu=ctx.lu)
    ctx.entities = getattr(ctx.lu, "entities", None) or extract_entities(raw)
    try:
        ctx.brief = extract_bot_brief(raw)
    except Exception:
        ctx.brief = None

    mem = memory
    if mem is None and user_id:
        try:
            mem = get_memory_engine()
        except Exception:
            mem = None

    intent_name = ctx.intent.primary.intent if ctx.intent and ctx.intent.primary else None
    if user_id and mem is not None:
        try:
            brief_d = None
            if ctx.entities is not None:
                brief_d = (getattr(ctx.entities, "raw", None) or {}).get("bot_brief")
            record_turn_learning(
                int(user_id),
                raw,
                brief=brief_d,
                intent_name=intent_name,
                features=list(getattr(ctx.entities, "features_requested", None) or []),
                memory=mem,
            )
            ctx.memory = recall(int(user_id), raw, memory=mem, intent_name=intent_name)
            new_req, notes = apply_full_memory(ctx.entities, ctx.memory, request=raw)
            ctx.enriched_request = new_req
            ctx.notes = list(notes)
        except Exception as exc:
            ctx.notes.append(f"memory_error:{type(exc).__name__}")
            ctx.enriched_request = raw
    else:
        ctx.enriched_request = raw

    return ctx


__all__ = ["TurnContext", "build_turn_context"]
