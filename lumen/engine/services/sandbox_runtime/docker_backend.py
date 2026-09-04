"""Hardened Docker sandbox — minimum production backend (runc or runsc via env)."""
from __future__ import annotations

import logging
import os
from typing import List

from .backend import SandboxBackend
from .network import ensure_egress_network, seccomp_profile_path
from .policy import assert_network_not_default_bridge, load_policy
from .types import SandboxHandle, SandboxProbe, SandboxSpec

logger = logging.getLogger(__name__)


class DockerSandboxBackend(SandboxBackend):
    name = "docker"
    strength = 50

    def probe(self) -> SandboxProbe:
        try:
            from lumen.engine.services.live_deployment.docker_process_driver import (
                docker_available,
            )
        except Exception as exc:
            return SandboxProbe(self.name, False, f"import:{type(exc).__name__}", self.strength)
        if not docker_available():
            return SandboxProbe(self.name, False, "docker_daemon_unavailable", self.strength)
        try:
            net = ensure_egress_network(create_if_missing=True)
            assert_network_not_default_bridge(net)
            try:
                from .egress import harden_network
                harden_network(net)
            except Exception as _eg:
                strict = (os.environ.get('TBE_EGRESS_STRICT') or '1').strip().lower() in {'1','true','yes','on'}
                if strict:
                    raise RuntimeError(f'egress_harden_failed:{type(_eg).__name__}') from _eg

        except Exception as exc:
            return SandboxProbe(self.name, False, str(exc)[:200], self.strength)
        return SandboxProbe(self.name, True, "docker_hardened_ok", self.strength)

    def start(self, spec: SandboxSpec) -> SandboxHandle:
        probe = self.probe()
        if not probe.available:
            return SandboxHandle(
                backend=self.name,
                deployment_id="",
                status="failed",
                message=f"sandbox_unavailable:{probe.reason}",
            )
        policy = load_policy()
        net = ensure_egress_network(create_if_missing=True)
        assert_network_not_default_bridge(net)
        try:
            from .egress import harden_network
            report = harden_network(net)
            if not report.get("ok"):
                strict = (os.environ.get("TBE_EGRESS_STRICT") or "1").strip().lower() in {
                    "1", "true", "yes", "on",
                }
                if strict:
                    return SandboxHandle(
                        backend=self.name,
                        deployment_id="",
                        status="failed",
                        message="egress_harden_failed:" + ",".join(str(x) for x in (report.get("errors") or [])[:4]),
                    )
        except Exception as _eg:
            strict = (os.environ.get("TBE_EGRESS_STRICT") or "1").strip().lower() in {
                "1", "true", "yes", "on",
            }
            if strict:
                return SandboxHandle(
                    backend=self.name,
                    deployment_id="",
                    status="failed",
                    message=f"egress_harden_failed:{type(_eg).__name__}",
                )
        os.environ["TBE_DOCKER_NETWORK"] = net
        sec = seccomp_profile_path()
        if sec and not (os.environ.get("TBE_DOCKER_SECCOMP") or "").strip():
            os.environ["TBE_DOCKER_SECCOMP"] = sec
        # Fail closed: Docker path (dev only) must not run without seccomp unless explicit opt-out
        allow_no = (os.environ.get("TBE_DOCKER_ALLOW_NO_SECCOMP") or "0").strip().lower() in {
            "1", "true", "yes", "on",
        }
        active_sec = (os.environ.get("TBE_DOCKER_SECCOMP") or "").strip()
        if not active_sec and not allow_no:
            return SandboxHandle(
                backend=self.name,
                deployment_id="",
                status="failed",
                message="docker_seccomp_required: set TBE_DOCKER_SECCOMP profile or only use Firecracker",
            )

        from lumen.engine.services.live_deployment.docker_process_driver import (
            DockerProcessDriver,
        )

        env = dict(spec.env_vars or {})
        env.setdefault("TELEGRAM_BOT_TOKEN", spec.bot_token)
        env.setdefault("BOT_TOKEN", spec.bot_token)
        os.environ.setdefault("TBE_DOCKER_MEMORY", policy.max_memory)
        os.environ.setdefault("TBE_DOCKER_CPUS", policy.max_cpus)
        os.environ.setdefault("TBE_DOCKER_PIDS", str(policy.max_pids))
        if spec.memory:
            os.environ["TBE_DOCKER_MEMORY"] = spec.memory
        if spec.cpus:
            os.environ["TBE_DOCKER_CPUS"] = spec.cpus

        status = DockerProcessDriver().deploy(
            spec.project_path,
            env_vars=env,
            service_name=spec.service_name or f"host-u{spec.user_id}",
        )
        st = str(getattr(status, "status", "") or "")
        dep = str(getattr(status, "deployment_id", "") or "")
        msg = str(getattr(status, "message", "") or "")
        running = "run" in st.lower() and "fail" not in st.lower()
        return SandboxHandle(
            backend=self.name,
            deployment_id=dep,
            container_or_vm_id=dep,
            status="running" if running else ("failed" if "fail" in st.lower() else st or "unknown"),
            message=msg,
            meta={
                "provider_status": st,
                "network": net,
                "seccomp": bool(sec),
                "runtime": os.environ.get("TBE_DOCKER_RUNTIME") or "runc",
            },
        )

    def stop(self, handle_or_id: str) -> SandboxHandle:
        from lumen.engine.services.live_deployment.docker_process_driver import (
            DockerProcessDriver,
        )
        status = DockerProcessDriver().stop(handle_or_id)
        return SandboxHandle(
            backend=self.name,
            deployment_id=handle_or_id,
            status=str(getattr(status, "status", "stopped") or "stopped"),
            message=str(getattr(status, "message", "") or ""),
        )

    def status(self, handle_or_id: str) -> SandboxHandle:
        from lumen.engine.services.live_deployment.docker_process_driver import (
            DockerProcessDriver,
        )
        status = DockerProcessDriver().status(handle_or_id)
        return SandboxHandle(
            backend=self.name,
            deployment_id=handle_or_id,
            status=str(getattr(status, "status", "") or "unknown"),
            message=str(getattr(status, "message", "") or ""),
        )

    def logs(self, handle_or_id: str, *, limit: int = 50) -> List[str]:
        from lumen.engine.services.live_deployment.docker_process_driver import (
            DockerProcessDriver,
        )
        try:
            return list(DockerProcessDriver().logs(handle_or_id, limit=limit) or [])
        except Exception:
            return []
