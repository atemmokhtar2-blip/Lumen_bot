"""gVisor (runsc) sandbox — userspace kernel isolation.

When runsc is registered as a Docker runtime, bot containers use
`--runtime=runsc` so syscalls are intercepted in userspace (Google-grade).
Stronger than runc on a shared kernel; weaker than Firecracker microVMs.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import List

from .backend import SandboxBackend
from .docker_backend import DockerSandboxBackend
from .types import SandboxHandle, SandboxProbe, SandboxSpec

logger = logging.getLogger(__name__)


def runsc_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        p = subprocess.run(
            ["docker", "info", "--format", "{{json .Runtimes}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        out = ((p.stdout or "") + (p.stderr or "")).lower()
        if "runsc" in out:
            return True
    except Exception:
        pass
    return bool(shutil.which("runsc"))


class GVisorSandboxBackend(SandboxBackend):
    name = "gvisor"
    strength = 85

    def __init__(self) -> None:
        self._inner = DockerSandboxBackend()

    def probe(self) -> SandboxProbe:
        if not runsc_available():
            return SandboxProbe(self.name, False, "runsc_runtime_not_registered", self.strength)
        p = self._inner.probe()
        if not p.available:
            return SandboxProbe(self.name, False, f"gvisor_docker:{p.reason}", self.strength)
        return SandboxProbe(self.name, True, "gvisor_runsc_ok", self.strength)

    def start(self, spec: SandboxSpec) -> SandboxHandle:
        probe = self.probe()
        if not probe.available:
            return SandboxHandle(
                backend=self.name,
                deployment_id="",
                status="failed",
                message=f"gvisor_unavailable:{probe.reason}",
            )
        os.environ["TBE_DOCKER_RUNTIME"] = "runsc"
        os.environ["TBE_SANDBOX_MODE"] = "gvisor"
        handle = self._inner.start(spec)
        handle.backend = self.name
        handle.meta = dict(handle.meta or {})
        handle.meta["runtime"] = "runsc"
        return handle

    def stop(self, handle_or_id: str) -> SandboxHandle:
        h = self._inner.stop(handle_or_id)
        h.backend = self.name
        return h

    def status(self, handle_or_id: str) -> SandboxHandle:
        h = self._inner.status(handle_or_id)
        h.backend = self.name
        return h

    def logs(self, handle_or_id: str, *, limit: int = 50) -> List[str]:
        return self._inner.logs(handle_or_id, limit=limit)
