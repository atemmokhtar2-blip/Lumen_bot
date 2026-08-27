"""Execution plan contract — Planner output consumed by Worker (Phase A+).

Cursor-class agents work from an explicit plan: files, tasks, acceptance.
This module is the shared schema (no LLM required to validate structure).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PlanTask:
    id: str
    title: str
    files: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    priority: int = 1  # 1 = must, 2 = should, 3 = nice
    depends_on: list[str] = field(default_factory=list)  # task ids this depends on
    parallel_group: str = ""  # non-empty → eligible for LangGraph Send fan-out


@dataclass
class ExecutionPlan:
    """Planner artifact stored on AgentState.extensions["execution_plan"]."""

    goal: str = ""
    language: str = "ar"
    deliverables: list[str] = field(default_factory=lambda: [
        "main.py", "app/handlers.py", "requirements.txt", "README.md", ".env.example",
    ])
    tasks: list[PlanTask] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    version: str = "a1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "language": self.language,
            "deliverables": list(self.deliverables),
            "tasks": [asdict(t) if not isinstance(t, dict) else t for t in self.tasks],
            "constraints": list(self.constraints),
            "features": list(self.features),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "ExecutionPlan":
        d = dict(d or {})
        tasks_raw = d.get("tasks") or []
        tasks: list[PlanTask] = []
        for i, t in enumerate(tasks_raw):
            if isinstance(t, dict):
                tasks.append(PlanTask(
                    id=str(t.get("id") or f"t{i}"),
                    title=str(t.get("title") or ""),
                    files=list(t.get("files") or []),
                    acceptance=list(t.get("acceptance") or []),
                    priority=int(t.get("priority") or 1),
                    depends_on=list(t.get("depends_on") or []),
                    parallel_group=str(t.get("parallel_group") or ""),
                ))
        return cls(
            goal=str(d.get("goal") or ""),
            language=str(d.get("language") or "ar"),
            deliverables=list(d.get("deliverables") or [
                "main.py", "app/handlers.py", "requirements.txt", "README.md", ".env.example",
            ]),
            tasks=tasks,
            constraints=list(d.get("constraints") or []),
            features=list(d.get("features") or []),
            version=str(d.get("version") or "a1"),
        )

    def to_worker_brief(self) -> str:
        """Compact brief injected into Cline Worker goal."""
        lines = [
            f"GOAL: {self.goal[:600]}",
            f"LANG: {self.language}",
            "DELIVERABLES: " + ", ".join(self.deliverables),
        ]
        if self.features:
            lines.append("FEATURES: " + ", ".join(self.features[:30]))
        if self.constraints:
            lines.append("CONSTRAINTS:")
            lines.extend(f"- {c}" for c in self.constraints[:12])
        if self.tasks:
            lines.append("TASKS (in order):")
            for t in self.tasks[:20]:
                files = ",".join(t.files[:6]) if t.files else "—"
                lines.append(f"  [{t.id}/P{t.priority}] {t.title} → files:{files}")
                for a in t.acceptance[:3]:
                    lines.append(f"      accept: {a}")
        return "\n".join(lines)


def build_plan_from_spec(
    *,
    goal: str,
    features: list[str] | None = None,
    constraints: list[str] | None = None,
    language: str = "ar",
    work_dir: str | None = None,
) -> ExecutionPlan:
    """Dynamic plan via multi-layer planner (intent → features → workspace → tasks)."""
    from .dynamic_planner import assemble_plan
    return assemble_plan(
        goal=goal or "",
        preferred_keys=features or [],
        constraints=constraints or [],
        language=language or "ar",
        work_dir=work_dir,
    )


__all__ = [
    "PlanTask",
    "ExecutionPlan",
    "build_plan_from_spec",
]
