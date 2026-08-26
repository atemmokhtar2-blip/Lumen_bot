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
) -> ExecutionPlan:
    """Deterministic plan skeleton from StrictSpec-like inputs (Planner baseline)."""
    feats = [str(f).strip() for f in (features or []) if str(f).strip()]
    tasks: list[PlanTask] = [
        PlanTask(
            id="scaffold",
            title="Create project scaffold and entrypoint",
            files=["main.py", "app/handlers.py", "requirements.txt", "README.md", ".env.example"],
            acceptance=[
                "main.py exists and is valid Python",
                "requirements.txt lists telegram dependency",
                "BOT_TOKEN read from environment",
            ],
            priority=1,
        ),
    ]
    if feats:
        tasks.append(PlanTask(
            id="features",
            title="Implement requested features as handlers/modules",
            files=["main.py"] + [f"modules/{f}.py" for f in feats[:12]],
            acceptance=[f"feature wired: {f}" for f in feats[:12]],
            priority=1,
        ))
    tasks.append(PlanTask(
        id="harden",
        title="Basic error handling and /start help text",
        files=["main.py"],
        acceptance=["/start responds", "unknown text has safe fallback"],
        priority=2,
    ))
    return ExecutionPlan(
        goal=(goal or "")[:2000],
        language=language or "ar",
        tasks=tasks,
        constraints=list(constraints or [])[:20],
        features=feats[:40],
    )


__all__ = [
    "PlanTask",
    "ExecutionPlan",
    "build_plan_from_spec",
]
