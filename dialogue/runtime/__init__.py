"""Maestro dialogue runtime — Phase 0 solid foundation.

Engines (in priority order when enabled):
  1. RasaEngine — if DIALOGUE_ENABLED and a trained model exists
  2. RuleEngine — always available, no extra deps (smart guided chat)

Generation never runs from here.
"""
from .contract import DialogueRequest, DialogueResponse, DialogueEngine
from .registry import get_dialogue_engine, handle_turn

__all__ = [
    "DialogueRequest",
    "DialogueResponse",
    "DialogueEngine",
    "get_dialogue_engine",
    "handle_turn",
]
