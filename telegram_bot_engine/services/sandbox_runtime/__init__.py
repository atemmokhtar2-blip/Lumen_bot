"""Strong isolation layer for generated bots.

Backends (strongest first):
  firecracker — microVM (KVM)
  dind        — dedicated Docker daemon (not host socket)
  docker      — hardened host Docker (image-only, seccomp, egress network)

All paths fail closed. No silent LocalProcess fallback from this package.
"""
from __future__ import annotations

from .backend import SandboxBackend
from .select import probe_all, select_sandbox_backend, start_sandboxed_bot
from .types import SandboxHandle, SandboxProbe, SandboxSpec

__all__ = [
    "SandboxBackend",
    "SandboxSpec",
    "SandboxHandle",
    "SandboxProbe",
    "select_sandbox_backend",
    "start_sandboxed_bot",
    "probe_all",
]
