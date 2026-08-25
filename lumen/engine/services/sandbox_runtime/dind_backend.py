"""Docker-in-Docker sandbox backend.

Uses a *dedicated* Docker API endpoint (TBE_DIND_HOST), never the host's
default socket for bot lifecycle when DinD is selected. User bot containers
never receive a docker.sock mount.

Setup (operator):
  - Run a DinD or rootless dockerd isolated from the Lumen process namespace
  - Export TBE_DIND_HOST=unix:///var/run/dind.sock  (or tcp+TLS)
  - TBE_SANDBOX_BACKEND=dind
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator, List

from .backend import SandboxBackend
from .docker_backend import DockerSandboxBackend
from .types import SandboxHandle, SandboxProbe, SandboxSpec

logger = logging.getLogger(__name__)


def _dind_host() -> str:
    return (os.environ.get("TBE_DIND_HOST") or "").strip()


@contextmanager
def _docker_host_override(host: str) -> Iterator[None]:
    prev = os.environ.get("DOCKER_HOST")
    os.environ["DOCKER_HOST"] = host
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("DOCKER_HOST", None)
        else:
            os.environ["DOCKER_HOST"] = prev


class DinDSandboxBackend(SandboxBackend):
    """Stronger than host-docker: bots managed only via isolated DinD daemon."""

    name = "dind"
    strength = 75

    def __init__(self) -> None:
        self._inner = DockerSandboxBackend()

    def probe(self) -> SandboxProbe:
        host = _dind_host()
        if not host:
            return SandboxProbe(
                self.name,
                False,
                "TBE_DIND_HOST not set (unix:///path/to/dind.sock or tcp+TLS)",
                self.strength,
            )
        # Refuse pointing "DinD" at the default host socket without explicit ack
        if "docker.sock" in host and "/dind" not in host:
            allow = (os.environ.get("TBE_DIND_ALLOW_HOST_SOCKET") or "0").strip().lower() in {
                "1", "true", "yes", "on",
            }
            if not allow:
                return SandboxProbe(
                    self.name,
                    False,
                    "refusing host docker.sock as DinD — set TBE_DIND_HOST to a dedicated daemon",
                    self.strength,
                )
        with _docker_host_override(host):
            p = self._inner.probe()
        if not p.available:
            return SandboxProbe(self.name, False, f"dind:{p.reason}", self.strength)
        return SandboxProbe(self.name, True, f"dind_ok host={host[:48]}", self.strength)

    def start(self, spec: SandboxSpec) -> SandboxHandle:
        probe = self.probe()
        if not probe.available:
            return SandboxHandle(
                backend=self.name,
                deployment_id="",
                status="failed",
                message=f"dind_unavailable:{probe.reason}",
            )
        host = _dind_host()
        with _docker_host_override(host):
            # Mark isolation for labels / logs
            os.environ["TBE_SANDBOX_MODE"] = "dind"
            handle = self._inner.start(spec)
        handle.backend = self.name
        handle.meta = dict(handle.meta or {})
        handle.meta["dind_host"] = host[:80]
        return handle

    def stop(self, handle_or_id: str) -> SandboxHandle:
        host = _dind_host()
        if not host:
            return SandboxHandle(self.name, handle_or_id, status="failed", message="no_dind_host")
        with _docker_host_override(host):
            h = self._inner.stop(handle_or_id)
        h.backend = self.name
        return h

    def status(self, handle_or_id: str) -> SandboxHandle:
        host = _dind_host()
        if not host:
            return SandboxHandle(self.name, handle_or_id, status="unknown", message="no_dind_host")
        with _docker_host_override(host):
            h = self._inner.status(handle_or_id)
        h.backend = self.name
        return h

    def logs(self, handle_or_id: str, *, limit: int = 50) -> List[str]:
        host = _dind_host()
        if not host:
            return []
        with _docker_host_override(host):
            return self._inner.logs(handle_or_id, limit=limit)
