"""Runtime Plane: workers, tools, containers, execution."""
from __future__ import annotations
from typing import Optional
from ..security.policy import PolicyEngine
from ..security.sandbox import SandboxExecutor

class RuntimePlane:
    def __init__(self, *, policy: Optional[PolicyEngine] = None,
                 sandbox: Optional[SandboxExecutor] = None) -> None:
        self.policy = policy or PolicyEngine()
        self.sandbox = sandbox or SandboxExecutor()
    def register_tool_handler(self, tool_name: str, handler) -> None:
        self.sandbox.register(tool_name, handler)

__all__ = ["RuntimePlane"]
