"""Strong isolation layer for generated bots (PaaS-grade).

Production / multi-tenant path (sole commercial path):
  firecracker — microVM (KVM + jailer)

Dev-only backends (explicit TBE_SANDBOX_BACKEND, never production fallback):
  gvisor — runsc userspace kernel
  dind   — dedicated Docker daemon (not host socket)
  docker — hardened runc + seccomp + AppArmor + egress network

Control:
  policy.py   — non-negotiable hard policy
  egress.py   — network + iptables baseline (container backends)
  supervisor.py — reap / lifetime enforcement
  select.py   — Firecracker-only in production; weak backends gated to dev

All production paths fail closed. No host-process execution from this package.
No silent fallback from Firecracker to weaker backends in multi-tenant/production.
"""
from __future__ import annotations

from .backend import SandboxBackend
from .select import (
    is_production_sandbox_path,
    probe_all,
    select_sandbox_backend,
    start_sandboxed_bot,
    start_permanent_host_bot,
)
from .types import SandboxHandle, SandboxProbe, SandboxSpec

__all__ = [
    "SandboxBackend",
    "SandboxSpec",
    "SandboxHandle",
    "SandboxProbe",
    "select_sandbox_backend",
    "start_sandboxed_bot",
    "start_permanent_host_bot",
    "probe_all",
    "is_production_sandbox_path",
]
