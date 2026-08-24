"""Strong isolation layer for generated bots (PaaS-grade).

Backends (strongest first):
  firecracker — microVM (KVM)
  gvisor      — runsc userspace kernel
  dind        — dedicated Docker daemon (not host socket)
  docker      — hardened runc + seccomp + AppArmor + egress network

Control:
  policy.py   — non-negotiable hard policy
  egress.py   — network + iptables baseline
  supervisor.py — reap / lifetime enforcement

All paths fail closed. No host-process execution from this package.
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
