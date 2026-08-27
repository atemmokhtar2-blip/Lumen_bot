"""Hierarchical Task Tree — real dependency graph for multi-agent execution."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class TaskRole(str, Enum):
    PLANNER = "planner"
    WORKER = "worker"
    CRITIC = "critic"
    REPAIR = "repair"
    ANY = "any"


@dataclass
class TaskNode:
    id: str
    title: str
    description: str = ""
    role: str = TaskRole.WORKER.value
    status: str = TaskStatus.PENDING.value
    depends_on: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    parallel_group: str = ""
    files: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    priority: int = 1
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    attempts: int = 0
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TaskNode":
        d = dict(data or {})
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex[:10]),
            title=str(d.get("title") or d.get("id") or "task"),
            description=str(d.get("description") or "")[:4000],
            role=str(d.get("role") or TaskRole.WORKER.value),
            status=str(d.get("status") or TaskStatus.PENDING.value),
            depends_on=[str(x) for x in (d.get("depends_on") or []) if str(x).strip()],
            children=[str(x) for x in (d.get("children") or []) if str(x).strip()],
            parallel_group=str(d.get("parallel_group") or ""),
            files=[str(x) for x in (d.get("files") or []) if str(x).strip()],
            acceptance=[str(x) for x in (d.get("acceptance") or []) if str(x).strip()],
            priority=int(d.get("priority") or 1),
            result=dict(d.get("result") or {}),
            error=str(d.get("error") or "")[:2000],
            attempts=int(d.get("attempts") or 0),
            max_attempts=max(1, int(d.get("max_attempts") or 3)),
            created_at=float(d.get("created_at") or time.time()),
            updated_at=float(d.get("updated_at") or time.time()),
        )


@dataclass
class TaskTree:
    root_id: str = "root"
    nodes: dict[str, TaskNode] = field(default_factory=dict)
    goal: str = ""
    version: int = 1
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.root_id not in self.nodes:
            self.nodes[self.root_id] = TaskNode(
                id=self.root_id, title="root", role=TaskRole.PLANNER.value, status=TaskStatus.DONE.value
            )

    def add(self, node: TaskNode, *, parent_id: str | None = None) -> TaskNode:
        self.nodes[node.id] = node
        pid = parent_id or self.root_id
        parent = self.nodes.get(pid)
        if parent is not None and node.id not in parent.children:
            parent.children.append(node.id)
        if pid != self.root_id and pid not in node.depends_on:
            node.depends_on.append(pid)
        self.refresh_readiness()
        return node

    def get(self, task_id: str) -> TaskNode | None:
        return self.nodes.get(task_id)

    def mark(self, task_id: str, status: TaskStatus | str, *, error: str = "", result: dict | None = None) -> TaskNode | None:
        node = self.nodes.get(task_id)
        if node is None:
            return None
        node.status = status.value if isinstance(status, TaskStatus) else str(status)
        node.updated_at = time.time()
        if error:
            node.error = error[:2000]
        if result is not None:
            node.result = dict(result)
        if node.status == TaskStatus.RUNNING.value:
            node.attempts = int(node.attempts or 0) + 1
        self.refresh_readiness()
        return node

    def reopen_failed(self, *, max_reopen: int = 20) -> list[str]:
        reopened: list[str] = []
        for node in self.nodes.values():
            if node.id == self.root_id or node.status != TaskStatus.FAILED.value:
                continue
            if int(node.attempts or 0) >= int(node.max_attempts or 3):
                continue
            node.status = TaskStatus.PENDING.value
            node.error = ""
            node.updated_at = time.time()
            reopened.append(node.id)
            if len(reopened) >= max_reopen:
                break
        self.refresh_readiness()
        return reopened

    def refresh_readiness(self) -> None:
        for node in self.nodes.values():
            if node.id == self.root_id:
                continue
            if node.status in {TaskStatus.DONE.value, TaskStatus.RUNNING.value, TaskStatus.SKIPPED.value, TaskStatus.FAILED.value}:
                continue
            deps_ok = all(
                (self.nodes.get(d) is None) or self.nodes[d].status == TaskStatus.DONE.value
                for d in node.depends_on
            )
            node.status = TaskStatus.READY.value if deps_ok else TaskStatus.BLOCKED.value
            node.updated_at = time.time()
        self.updated_at = time.time()

    def ready_tasks(self) -> list[TaskNode]:
        out = [n for n in self.nodes.values() if n.id != self.root_id and n.status == TaskStatus.READY.value]
        out.sort(key=lambda n: (int(n.priority or 1), n.created_at))
        return out

    def failed_tasks(self) -> list[TaskNode]:
        return [n for n in self.nodes.values() if n.id != self.root_id and n.status == TaskStatus.FAILED.value]

    def is_complete(self) -> bool:
        workers = [n for n in self.nodes.values() if n.id != self.root_id]
        return bool(workers) and all(n.status in {TaskStatus.DONE.value, TaskStatus.SKIPPED.value} for n in workers)

    def has_unrecoverable_failures(self) -> bool:
        return any(int(n.attempts or 0) >= int(n.max_attempts or 3) for n in self.failed_tasks())

    def parallel_wave(self) -> list[TaskNode]:
        ready = self.ready_tasks()
        if not ready:
            return []
        groups: dict[str, list[TaskNode]] = {}
        for n in ready:
            if n.parallel_group:
                groups.setdefault(n.parallel_group, []).append(n)
        best: list[TaskNode] = []
        for members in groups.values():
            chosen: list[TaskNode] = []
            used: set[str] = set()
            for n in members:
                files = {f for f in (n.files or []) if f}
                if files & used:
                    continue
                chosen.append(n)
                used |= files
            if len(chosen) > len(best):
                best = chosen
        if len(best) >= 2:
            return best
        return [ready[0]]

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for n in self.nodes.values():
            if n.id == self.root_id:
                continue
            counts[n.status] = counts.get(n.status, 0) + 1
        return {
            "goal": (self.goal or "")[:200],
            "total": sum(counts.values()),
            "counts": counts,
            "complete": self.is_complete(),
            "ready": [n.id for n in self.ready_tasks()[:20]],
            "failed": [n.id for n in self.failed_tasks()[:20]],
        }

    def worker_brief(self, task_id: str) -> str:
        node = self.nodes.get(task_id)
        if node is None:
            return ""
        lines = [f"TASK [{node.id}]: {node.title}", f"DESC: {(node.description or node.title)[:1200]}"]
        if node.files:
            lines.append("FILES: " + ", ".join(node.files[:20]))
        if node.acceptance:
            lines.append("ACCEPTANCE:")
            lines.extend(f"- {a}" for a in node.acceptance[:12])
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_id": self.root_id,
            "goal": self.goal,
            "version": self.version,
            "updated_at": self.updated_at,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "summary": self.summary(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TaskTree":
        d = dict(data or {})
        nodes = {
            str(k): TaskNode.from_dict(v if isinstance(v, dict) else {})
            for k, v in (d.get("nodes") or {}).items()
        }
        tree = cls(
            root_id=str(d.get("root_id") or "root"),
            nodes=nodes,
            goal=str(d.get("goal") or ""),
            version=int(d.get("version") or 1),
            updated_at=float(d.get("updated_at") or time.time()),
        )
        if tree.root_id not in tree.nodes:
            tree.nodes[tree.root_id] = TaskNode(
                id=tree.root_id, title="root", role=TaskRole.PLANNER.value, status=TaskStatus.DONE.value
            )
        tree.refresh_readiness()
        return tree

    @classmethod
    def from_execution_plan(cls, plan: Any, *, goal: str = "") -> "TaskTree":
        goal_s = goal or str(getattr(plan, "goal", "") or "")
        tree = cls(goal=goal_s)
        tasks = list(getattr(plan, "tasks", None) or [])
        prev_id: str | None = None
        for i, t in enumerate(tasks):
            raw = t.to_dict() if hasattr(t, "to_dict") else (dict(t) if isinstance(t, dict) else {})
            if not raw:
                continue
            tid = str(raw.get("id") or f"t{i+1}")
            depends = list(raw.get("depends_on") or [])
            # Only linear-chain when planner omitted dependencies
            if not depends and prev_id:
                depends = [prev_id]
            tree.add(
                TaskNode(
                    id=tid,
                    title=str(raw.get("title") or tid),
                    description=str(raw.get("description") or raw.get("title") or "")[:2000],
                    role=TaskRole.WORKER.value,
                    depends_on=depends,
                    files=[str(x) for x in (raw.get("files") or []) if str(x).strip()],
                    acceptance=[str(x) for x in (raw.get("acceptance") or []) if str(x).strip()],
                    priority=int(raw.get("priority") or 1),
                    parallel_group=str(raw.get("parallel_group") or ""),
                ),
                parent_id=tree.root_id,
            )
            prev_id = tid
        tree.refresh_readiness()
        return tree

    @classmethod
    def default_bot_tree(cls, *, goal: str, features: Iterable[str] | None = None, work_dir: str | None = None) -> "TaskTree":
        """Build tree via dynamic planner (intent-aware, not Telegram-only template)."""
        from .dynamic_planner import assemble_plan
        plan = assemble_plan(goal=goal or "", preferred_keys=list(features or []), work_dir=work_dir)
        return cls.from_execution_plan(plan, goal=plan.goal)



__all__ = ["TaskStatus", "TaskRole", "TaskNode", "TaskTree"]
