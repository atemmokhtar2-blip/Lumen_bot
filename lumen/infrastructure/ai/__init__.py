"""AI infrastructure adapters (Cline / multi-agent / LLM providers).

Public boundary for presentation and application layers that need agent turns.
Concrete engines still live under lumen.engine during migration.
"""
from lumen.infrastructure.ai.engine_turn import EngineTurnResult, handle_user_turn

__all__ = ["EngineTurnResult", "handle_user_turn"]
