"""Select the strongest available sandbox backend (fail-closed)."""
from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

from .backend import SandboxBackend
from .dind_backend import DinDSandboxBackend
from .docker_backend import DockerSandboxBackend
from .firecracker_backend import FirecrackerSandboxBackend
from .gvisor_backend import GVisorSandboxBackend
from .types import SandboxProbe

logger = logging.getLogger(__name__)


def _requested_backend() -> str:
    return (os.environ.get("TBE_SANDBOX_BACKEND") or "auto").strip().lower()


def _all_backends() -> List[SandboxBackend]:
    # Strongest first for auto selection
    return [
        FirecrackerSandboxBackend(),  # microVM
        GVisorSandboxBackend(),       # userspace kernel
        DinDSandboxBackend(),         # dedicated docker daemon
        DockerSandboxBackend(),       # hardened runc (minimum)
    ]


def probe_all() -> List[SandboxProbe]:
    return [b.probe() for b in _all_backends()]


def select_sandbox_backend(*, require_available: bool = True) -> Tuple[SandboxBackend, SandboxProbe]:
    """TBE_SANDBOX_BACKEND=auto|firecracker|gvisor|dind|docker"""
    req = _requested_backend()
    backends = {b.name: b for b in _all_backends()}

    if req in backends:
        b = backends[req]
        p = b.probe()
        if require_available and not p.available:
            raise RuntimeError(f"sandbox_backend_unavailable:{req}:{p.reason}")
        return b, p

    for b in _all_backends():
        p = b.probe()
        if p.available:
            logger.info("sandbox selected backend=%s reason=%s", b.name, p.reason)
            return b, p

    reasons = "; ".join(f"{x.name}:{x.probe().reason}" for x in _all_backends())
    raise RuntimeError(
        "no_sandbox_backend_available: "
        f"{reasons}. Need Docker+egress network, or gVisor runsc, or Firecracker+KVM."
    )


def start_sandboxed_bot(
    *,
    project_path: str,
    bot_token: str,
    user_id: int = 0,
    service_name: str = "",
    env_vars: Optional[dict] = None,
):
    from .egress import harden_network
    from .types import SandboxSpec

    # Always harden network before start — strict mode raises
    harden_network(os.environ.get("TBE_DOCKER_NETWORK") or "")

    backend, probe = select_sandbox_backend(require_available=True)
    spec = SandboxSpec(
        project_path=str(project_path),
        bot_token=bot_token,
        user_id=int(user_id or 0),
        service_name=service_name or f"host-u{user_id}",
        env_vars=dict(env_vars or {}),
    )
    handle = backend.start(spec)
    handle.meta = dict(handle.meta or {})
    handle.meta["probe"] = probe.reason
    handle.meta["backend"] = backend.name
    return backend, handle
