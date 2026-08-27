"""Official role contracts for the integrated multi-agent system.

Canonical names (OpenHands / Cursor-style):
  Planner  = ArchitectAgent  — builds ExecutionPlan + TaskTree
  Worker   = BuilderAgent    — coding_agent / Cline agent_loop
  Critic   = CriticAgent     — acceptance + QA / findings
  Reviewer = CriticAgent     — alias

LangGraph nodes map:
  plan → Planner, work → Worker, critique → Critic
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable, Any, Optional

from ..state import AgentState


@runtime_checkable
class PlannerRole(Protocol):
    """Produces ExecutionPlan + TaskTree; does not write project files."""

    name: str
    role: str

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState: ...


@runtime_checkable
class WorkerRole(Protocol):
    """Executes coding tasks against work_dir via real tools."""

    name: str
    role: str

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState: ...


@runtime_checkable
class CriticRole(Protocol):
    """Reviews build output; sets qa_passed / findings."""

    name: str
    role: str

    def run(self, state: AgentState, *, context: Optional[dict[str, Any]] = None) -> AgentState: ...


ROLE_ALIASES = {
    "planner": "architect",
    "worker": "builder",
    "critic": "critic",
    "reviewer": "critic",
}

GRAPH_ROLE_MAP = {
    "plan": "planner",
    "work": "worker",
    "critique": "critic",
    "repair": "worker",
}


def resolve_role_name(name: str) -> str:
    n = (name or "").strip().lower()
    return ROLE_ALIASES.get(n, n)
