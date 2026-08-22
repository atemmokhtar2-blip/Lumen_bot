"""Agent state for the free Cline path — messages, steps, stop reasons.

This is the control state of the autonomous coding loop, not catalog IR.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMessage:
    role: str  # system | user | assistant | tool
    content: str
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_name:
            d["tool_name"] = self.tool_name
        if self.tool_args is not None:
            d["tool_args"] = self.tool_args
        if self.tool_result is not None:
            d["tool_result"] = self.tool_result
        return d


@dataclass
class AgentStep:
    index: int
    thought: str = ""
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: dict[str, Any] = field(default_factory=dict)
    raw_model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "thought": self.thought[:2000],
            "tool_name": self.tool_name,
            "tool_args": dict(self.tool_args or {}),
            "tool_result": dict(self.tool_result or {}),
            "raw_model": (self.raw_model or "")[:500],
        }


@dataclass
class AgentState:
    work_dir: str
    goal: str
    messages: list[AgentMessage] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    stop_reason: str = ""  # completed | max_steps | error | no_model | aborted
    ok: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_system(self, text: str) -> None:
        self.messages.append(AgentMessage(role="system", content=text))

    def add_user(self, text: str) -> None:
        self.messages.append(AgentMessage(role="user", content=text))

    def add_assistant(self, text: str) -> None:
        self.messages.append(AgentMessage(role="assistant", content=text))

    def add_tool_result(self, name: str, result: dict[str, Any]) -> None:
        self.messages.append(
            AgentMessage(
                role="tool",
                content=str(result)[:8000],
                tool_name=name,
                tool_result=result,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_dir": self.work_dir,
            "goal": self.goal[:2000],
            "steps": [s.to_dict() for s in self.steps],
            "files_written": list(self.files_written),
            "stop_reason": self.stop_reason,
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "message_count": len(self.messages),
        }


__all__ = ["AgentMessage", "AgentStep", "AgentState"]
