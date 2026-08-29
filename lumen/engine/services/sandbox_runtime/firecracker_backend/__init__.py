"""Firecracker microVM backend — public surface (import-stable).

External code keeps:
  from lumen.engine.services.sandbox_runtime.firecracker_backend import FirecrackerSandboxBackend
"""
from __future__ import annotations

from .backend import FirecrackerSandboxBackend

__all__ = ["FirecrackerSandboxBackend"]
