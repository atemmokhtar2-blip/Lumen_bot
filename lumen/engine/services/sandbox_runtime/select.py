"""Select sandbox backend — Firecracker is the sole production path.

Production / multi-tenant:
  Firecracker only. No silent fallback to gVisor / DinD / Docker.

Dev / local / test:
  Explicit TBE_SANDBOX_BACKEND=gvisor|dind|docker honored.
  auto picks strongest available (Firecracker first).

Control:
  TBE_SANDBOX_BACKEND=auto|firecracker|gvisor|dind|docker
  TBE_MULTI_TENANT=1 (default) + non-dev ENVIRONMENT → production path
"""
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

_PRIMARY = "firecracker"
_DEV_ONLY = frozenset({"gvisor", "dind", "docker"})


def _requested_backend() -> str:
    return (os.environ.get("TBE_SANDBOX_BACKEND") or "auto").strip().lower()


def _flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def _env_name() -> str:
    return (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").strip().lower()


def _is_dev_environment() -> bool:
    return _env_name() in {"dev", "development", "local", "test"}


def _is_multi_tenant() -> bool:
    return _flag("TBE_MULTI_TENANT", "1")


def is_production_sandbox_path() -> bool:
    """True when hosting must use Firecracker only (no weak fallback)."""
    return _is_multi_tenant() or not _is_dev_environment()


def _primary_backend() -> SandboxBackend:
    return FirecrackerSandboxBackend()


def _dev_backends() -> List[SandboxBackend]:
    """Weaker backends — selectable only outside production path."""
    return [
        GVisorSandboxBackend(),
        DinDSandboxBackend(),
        DockerSandboxBackend(),
    ]


def _all_backends() -> List[SandboxBackend]:
    # Strongest first (used for probe_all and dev auto)
    return [_primary_backend()] + _dev_backends()


def probe_all() -> List[SandboxProbe]:
    return [b.probe() for b in _all_backends()]


def select_sandbox_backend(*, require_available: bool = True) -> Tuple[SandboxBackend, SandboxProbe]:
    """Select backend.

    Production/multi-tenant → Firecracker only.
    Dev → honor TBE_SANDBOX_BACKEND or auto (strongest available).
    """
    req = _requested_backend()
    prod = is_production_sandbox_path()

    if prod:
        if req in _DEV_ONLY:
            raise RuntimeError(
                f"production_requires_firecracker: "
                f"TBE_SANDBOX_BACKEND={req} is dev-only; "
                f"set TBE_SANDBOX_BACKEND=firecracker (or auto)"
            )
        b = _primary_backend()
        p = b.probe()
        if require_available and not p.available:
            raise RuntimeError(
                f"sandbox_backend_unavailable:firecracker:{p.reason}. "
                "Production hosting requires Firecracker+KVM+jailer+kernel+rootfs. "
                "No fallback to gVisor/Docker."
            )
        logger.info("sandbox selected backend=firecracker production=1 reason=%s", p.reason)
        return b, p

    # ── Dev / local / test ──────────────────────────────────────────────
    backends = {b.name: b for b in _all_backends()}

    if req in backends:
        b = backends[req]
        p = b.probe()
        if require_available and not p.available:
            raise RuntimeError(f"sandbox_backend_unavailable:{req}:{p.reason}")
        if req in _DEV_ONLY:
            logger.warning(
                "sandbox selected dev-only backend=%s — not for production multi-tenant",
                req,
            )
        else:
            logger.info("sandbox selected backend=%s reason=%s", b.name, p.reason)
        return b, p

    # auto: strongest available
    for b in _all_backends():
        p = b.probe()
        if p.available:
            logger.info("sandbox selected backend=%s reason=%s (dev auto)", b.name, p.reason)
            return b, p

    reasons = "; ".join(f"{x.name}:{x.probe().reason}" for x in _all_backends())
    raise RuntimeError(
        "no_sandbox_backend_available: "
        f"{reasons}. Need Firecracker+KVM (preferred), or gVisor/Docker in dev."
    )


def start_sandboxed_bot(
    *,
    project_path: str,
    bot_token: str,
    user_id: int = 0,
    service_name: str = "",
    env_vars: Optional[dict] = None,
):
    from .types import SandboxSpec

    backend, probe = select_sandbox_backend(require_available=True)

    # Container backends need Docker egress network hardening.
    # Firecracker uses TAP/netns — do not require Docker network there.
    if backend.name != "firecracker":
        from .egress import harden_network

        harden_network(os.environ.get("TBE_DOCKER_NETWORK") or "")

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
    handle.meta["production_path"] = is_production_sandbox_path()
    return backend, handle
