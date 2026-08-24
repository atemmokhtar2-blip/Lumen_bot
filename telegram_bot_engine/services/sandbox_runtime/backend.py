"""SandboxBackend — contract for strong isolation of generated bots."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .types import SandboxHandle, SandboxProbe, SandboxSpec


class SandboxBackend(ABC):
    """Run untrusted generated bot code with OS/container/VM isolation."""

    name: str = "abstract"
    strength: int = 0

    @abstractmethod
    def probe(self) -> SandboxProbe:
        """Whether this backend can run on this host right now."""

    @abstractmethod
    def start(self, spec: SandboxSpec) -> SandboxHandle:
        """Start isolated bot; never returns success without real isolation."""

    @abstractmethod
    def stop(self, handle_or_id: str) -> SandboxHandle:
        """Stop and reclaim resources."""

    @abstractmethod
    def status(self, handle_or_id: str) -> SandboxHandle:
        """Current status."""

    @abstractmethod
    def logs(self, handle_or_id: str, *, limit: int = 50) -> List[str]:
        """Recent logs (caller must redact secrets)."""
