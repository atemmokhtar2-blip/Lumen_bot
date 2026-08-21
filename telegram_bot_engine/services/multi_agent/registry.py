"""Agent registry — add/replace agents without editing the orchestrator core."""
from __future__ import annotations

import logging
import threading
from typing import Iterable, Optional

from .protocol import Agent

logger = logging.getLogger(__name__)


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._lock = threading.RLock()

    def register(self, agent: Agent, *, replace: bool = True) -> None:
        with self._lock:
            key = agent.name or f"{agent.role}:{id(agent)}"
            if key in self._agents and not replace:
                raise ValueError(f"agent already registered: {key}")
            self._agents[key] = agent
            logger.debug("registered agent %s order=%s", key, agent.order)

    def unregister(self, name: str) -> None:
        with self._lock:
            self._agents.pop(name, None)

    def get(self, name: str) -> Optional[Agent]:
        with self._lock:
            return self._agents.get(name)

    def pipeline(self) -> list[Agent]:
        """Agents sorted by order for sequential orchestration."""
        with self._lock:
            return sorted(self._agents.values(), key=lambda a: (int(a.order), a.name))

    def clear(self) -> None:
        with self._lock:
            self._agents.clear()

    def names(self) -> list[str]:
        with self._lock:
            return list(self._agents.keys())


def build_default_registry() -> AgentRegistry:
    from .roles.router import RouterAgent
    from .roles.architect import ArchitectAgent
    from .roles.builder import BuilderAgent
    from .roles.critic import CriticAgent

    reg = AgentRegistry()
    for agent in (RouterAgent(), ArchitectAgent(), BuilderAgent(), CriticAgent()):
        reg.register(agent)
    return reg


_default_registry: AgentRegistry | None = None
_reg_lock = threading.Lock()


def get_registry() -> AgentRegistry:
    global _default_registry
    with _reg_lock:
        if _default_registry is None:
            _default_registry = build_default_registry()
        return _default_registry


def set_registry(reg: AgentRegistry) -> None:
    global _default_registry
    with _reg_lock:
        _default_registry = reg
