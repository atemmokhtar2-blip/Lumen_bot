"""Agent protocol — every role is a pluggable agent. No Telegram coupling."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from .state import AgentState


class Agent(ABC):
    """Single-responsibility agent. Reads/writes Blackboard state only."""

    role: str = "AGENT"
    name: str = "base"
    # Pipeline order (lower runs earlier). Gaps allowed for future agents.
    order: int = 100

    @abstractmethod
    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState:
        """Execute role logic and return updated state (same instance or new)."""

    def can_run(self, state: AgentState) -> bool:
        """Override to skip agent based on state (default: always run)."""
        return True

    def __repr__(self) -> str:
        return f"<Agent {self.name} role={self.role} order={self.order}>"
