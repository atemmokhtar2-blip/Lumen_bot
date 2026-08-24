"""Central isolation policy for running untrusted generated bot code.

All entry points that execute user/tenant code MUST consult this module.
Defaults are fail-closed for multi-tenant / production:
  - Docker required
  - LocalProcessDriver denied unless explicit opt-in AND non-production
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def environment_name() -> str:
    return (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").strip().lower()


def is_dev_environment() -> bool:
    # Empty / unset ENVIRONMENT is treated as production (fail-closed).
    return environment_name() in {"dev", "development", "local", "test"}


def is_multi_tenant() -> bool:
    # Default ON — SaaS posture
    return _flag("TBE_MULTI_TENANT", "1")


@dataclass(frozen=True)
class IsolationDecision:
    require_docker: bool
    allow_local: bool
    reason: str

    @property
    def may_use_local(self) -> bool:
        return self.allow_local and not self.require_docker


def decide_isolation() -> IsolationDecision:
    """Binding isolation decision — Docker only, no host-process alternative.

    Production-grade rule: generated/untrusted bot code never runs on the host.
    Local process is never allowed by policy (select_process_driver / LiveRunner refuse).
    """
    multi = is_multi_tenant()
    dev = is_dev_environment()
    require = True
    allow = False
    reason = (
        f"docker_only multi_tenant={multi} dev={dev} "
        f"require_docker={require} allow_local={allow}"
    )
    return IsolationDecision(require_docker=require, allow_local=allow, reason=reason)



def assert_local_process_allowed() -> None:
    """Raise RuntimeError if LocalProcessDriver must not run.

    Dual gate: isolation allow_local AND explicit TBE_FORCE_LOCAL_PROCESS=1.
    Prevents any accidental host execution of model-generated code.
    """
    d = decide_isolation()
    force = _flag("TBE_FORCE_LOCAL_PROCESS", "0")
    if not d.allow_local or not force:
        raise RuntimeError(
            "local_process_denied: Docker isolation required for untrusted bot code. "
            f"({d.reason}; force_local={force}) Set ENVIRONMENT=dev, "
            "TBE_MULTI_TENANT=0, TBE_ALLOW_LOCAL_PROCESS=1, and "
            "TBE_FORCE_LOCAL_PROCESS=1 only for trusted local development."
        )


def select_process_driver():
    """Return a DeploymentProvider-compatible driver via sandbox_runtime.

    Prefer sandbox_runtime backends (firecracker / dind / hardened docker).
    Local process is never selected here.
    """
    decision = decide_isolation()
    try:
        from telegram_bot_engine.services.sandbox_runtime import select_sandbox_backend
        from telegram_bot_engine.services.sandbox_runtime.docker_backend import DockerSandboxBackend
        backend, probe = select_sandbox_backend(require_available=True)
        # Adapter: backends that wrap DockerProcessDriver expose same deploy API via adapter
        if backend.name in {"docker", "dind"}:
            from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
                DockerProcessDriver,
            )
            # Ensure DinD host override is applied by using start_sandboxed path from HostingService;
            # for legacy callers still using deploy(), return DockerProcessDriver under correct host.
            if backend.name == "dind":
                import os
                host = (os.environ.get("TBE_DIND_HOST") or "").strip()
                if host:
                    os.environ["DOCKER_HOST"] = host
            return DockerProcessDriver(), decision
        # Firecracker: thin adapter implementing deploy/stop/status/logs
        return _FirecrackerDriverAdapter(backend), decision
    except Exception as exc:
        raise RuntimeError(
            "sandbox_required_but_unavailable: isolated runtime required; "
            f"({decision.reason}; {exc})"
        ) from exc


class _FirecrackerDriverAdapter:
    """Adapt FirecrackerSandboxBackend to DeploymentProvider surface."""

    name = "firecracker"

    def __init__(self, backend) -> None:
        self._backend = backend

    def deploy(self, project_path, *, env_vars=None, service_name="generated-bot"):
        from telegram_bot_engine.engines.generators.live_deployment.report_data import (
            DEPLOY_FAILED,
            DEPLOY_RUNNING,
            DeploymentStatus,
        )
        from telegram_bot_engine.services.sandbox_runtime.types import SandboxSpec
        token = ""
        env = dict(env_vars or {})
        token = env.get("BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN") or ""
        handle = self._backend.start(
            SandboxSpec(
                project_path=str(project_path),
                bot_token=token,
                service_name=service_name,
                env_vars=env,
            )
        )
        if not handle.ok:
            return DeploymentStatus(
                provider=self.name,
                deployment_id=handle.deployment_id or "",
                status=DEPLOY_FAILED,
                message=handle.message or "firecracker_failed",
            )
        return DeploymentStatus(
            provider=self.name,
            deployment_id=handle.deployment_id,
            status=DEPLOY_RUNNING,
            message=handle.message or "running",
        )

    def status(self, deployment_id: str):
        from telegram_bot_engine.engines.generators.live_deployment.report_data import (
            DEPLOY_RUNNING,
            DEPLOY_STOPPED,
            DeploymentStatus,
        )
        h = self._backend.status(deployment_id)
        st = DEPLOY_RUNNING if h.status == "running" else DEPLOY_STOPPED
        return DeploymentStatus(provider=self.name, deployment_id=deployment_id, status=st, message=h.message)

    def stop(self, deployment_id: str):
        from telegram_bot_engine.engines.generators.live_deployment.report_data import (
            DEPLOY_STOPPED,
            DeploymentStatus,
        )
        h = self._backend.stop(deployment_id)
        return DeploymentStatus(provider=self.name, deployment_id=deployment_id, status=DEPLOY_STOPPED, message=h.message)

    def restart(self, deployment_id: str):
        return self.stop(deployment_id)

    def logs(self, deployment_id: str, *, limit: int = 50):
        return list(self._backend.logs(deployment_id, limit=limit) or [])


def require_docker_runtime() -> None:
    """Raise if current policy forbids running without Docker."""
    d = decide_isolation()
    if d.require_docker or not d.allow_local:
        from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
            docker_available,
        )
        if not docker_available():
            raise RuntimeError(
                "docker_required_but_unavailable: "
                f"({d.reason})"
            )


__all__ = [
    "IsolationDecision",
    "decide_isolation",
    "assert_local_process_allowed",
    "select_process_driver",
    "require_docker_runtime",
    "is_multi_tenant",
    "is_dev_environment",
    "environment_name",
]
