"""Permanent-host orchestration plane — Firecracker only.

This is the integration point between the control plane (HostingService / worker)
and the isolation backend. There is no Docker choice on the permanent-host path:
commercial hosting always uses Firecracker microVMs (see start_permanent_host_bot).

The generation pipeline orchestrator (engine/pipeline/orchestrator.py) builds
code; it does not run customer bots. Bot runtime is exclusively this module +
HostingService.start / worker.process_one.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("tbe.hosting.orchestration")


def select_permanent_backend():
    """Return Firecracker backend for permanent hosts. Raises if unavailable."""
    from lumen.engine.services.sandbox_runtime.firecracker_backend import (
        FirecrackerSandboxBackend,
    )

    backend = FirecrackerSandboxBackend()
    probe = backend.probe()
    if not probe.available:
        raise RuntimeError(
            f"permanent_host_requires_firecracker:{probe.reason}. "
            "Docker is not an alternative for permanent hosting."
        )
    return backend, probe


def start_host(
    *,
    project_path: str,
    bot_token: str,
    user_id: int = 0,
    service_name: str = "",
    env_vars: Optional[dict[str, str]] = None,
) -> tuple[Any, Any]:
    """Start a permanent hosted bot (Firecracker only)."""
    from lumen.engine.services.sandbox_runtime import start_permanent_host_bot

    return start_permanent_host_bot(
        project_path=project_path,
        bot_token=bot_token,
        user_id=user_id,
        service_name=service_name,
        env_vars=env_vars,
    )


def stop_host(deployment_id: str) -> None:
    from lumen.engine.services.sandbox_runtime.firecracker_backend import (
        FirecrackerSandboxBackend,
    )

    FirecrackerSandboxBackend().stop((deployment_id or "").strip())


__all__ = ["select_permanent_backend", "start_host", "stop_host"]
