"""Central isolation policy for running untrusted generated bot code.

All entry points that execute user/tenant code MUST consult this module.

Policy (practical SaaS host):
  1) Prefer Docker isolation when the daemon is available.
  2) If Docker is missing/fails, allow LocalProcessDriver only when explicitly
     opted in (dual gate) OR when TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER=1 (default).
  3) Local process always applies OS resource limits (RLIMIT_*).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def environment_name() -> str:
    return (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").strip().lower()


def is_dev_environment() -> bool:
    return environment_name() in {"dev", "development", "local", "test"}


def is_multi_tenant() -> bool:
    return _flag("TBE_MULTI_TENANT", "1")


@dataclass(frozen=True)
class IsolationDecision:
    require_docker: bool
    allow_local: bool
    reason: str

    @property
    def may_use_local(self) -> bool:
        return self.allow_local


def decide_isolation() -> IsolationDecision:
    """Docker preferred; local fallback allowed when configured.

    Dual explicit gate (always allows local, skips docker preference):
      TBE_ALLOW_LOCAL_PROCESS=1 AND TBE_FORCE_LOCAL_PROCESS=1

    Automatic fallback when Docker is down (default ON for single-host ops):
      TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER=1  (default "1")
    """
    multi = is_multi_tenant()
    dev = is_dev_environment()
    dual = _flag("TBE_ALLOW_LOCAL_PROCESS", "0") and _flag("TBE_FORCE_LOCAL_PROCESS", "0")
    # Default ON so hosts without Docker can still live-run generated bots.
    fallback = _flag("TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER", "1")

    if dual:
        return IsolationDecision(
            require_docker=False,
            allow_local=True,
            reason=f"explicit_local multi_tenant={multi} dev={dev}",
        )

    return IsolationDecision(
        require_docker=True,  # try Docker first
        allow_local=fallback,  # fall back if Docker missing/fails
        reason=(
            f"docker_preferred local_fallback={fallback} "
            f"multi_tenant={multi} dev={dev}"
        ),
    )


def assert_local_process_allowed() -> None:
    """Raise if LocalProcessDriver must not run under current policy."""
    d = decide_isolation()
    if not d.allow_local:
        raise RuntimeError(
            "local_process_denied: set TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER=1 "
            "or TBE_ALLOW_LOCAL_PROCESS=1 + TBE_FORCE_LOCAL_PROCESS=1. "
            f"({d.reason})"
        )


def select_process_driver():
    """Return DeploymentProvider: Docker when available, else local if allowed."""
    decision = decide_isolation()
    try:
        from lumen.engine.engines.generators.live_deployment.docker_process_driver import (
            DockerProcessDriver,
            docker_available,
        )
        if decision.require_docker and docker_available():
            return DockerProcessDriver(), decision
    except Exception:
        pass

    if decision.allow_local:
        from lumen.engine.engines.generators.live_deployment.local_process_driver import (
            LocalProcessDriver,
        )
        return LocalProcessDriver(), decision

    raise RuntimeError(
        "sandbox_required_but_unavailable: isolated runtime required; "
        f"({decision.reason})"
    )


def require_docker_runtime() -> None:
    d = decide_isolation()
    if d.require_docker and not d.allow_local:
        try:
            from lumen.engine.engines.generators.live_deployment.docker_process_driver import (
                docker_available,
            )
            if not docker_available():
                raise RuntimeError(
                    "docker_required_but_unavailable: "
                    f"({d.reason})"
                )
        except ImportError as exc:
            raise RuntimeError(f"docker_required_but_unavailable: {exc}") from exc


__all__ = [
    "IsolationDecision",
    "decide_isolation",
    "assert_local_process_allowed",
    "select_process_driver",
    "require_docker_runtime",
    "is_dev_environment",
    "is_multi_tenant",
    "environment_name",
]
