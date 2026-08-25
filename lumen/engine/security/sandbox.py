"""SandboxExecutor — sole performer of tool side effects after Policy.ALLOW."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

@dataclass
class SandboxResult:
    ok: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

ExecutorFn = Callable[..., SandboxResult]

class SandboxExecutor:
    def __init__(self) -> None:
        self._handlers: Dict[str, ExecutorFn] = {}
    def register(self, tool_name: str, handler: ExecutorFn) -> None:
        if not tool_name or not callable(handler):
            raise ValueError("tool_name and callable handler required")
        self._handlers[tool_name] = handler
    def has(self, tool_name: str) -> bool:
        return tool_name in self._handlers
    def execute(self, tool_name: str, params: Dict[str, Any], *,
                user_id: int = 0, user_data: Optional[Dict[str, Any]] = None) -> SandboxResult:
        handler = self._handlers.get(tool_name)
        if handler is None:
            return SandboxResult(ok=False, message=f"no sandbox handler for '{tool_name}'", error="unregistered_tool")
        try:
            return handler(params, user_id=user_id, user_data=user_data or {})
        except Exception as exc:
            return SandboxResult(ok=False, message=f"{type(exc).__name__}: {exc}", error=type(exc).__name__)

__all__ = ["SandboxResult", "SandboxExecutor"]
