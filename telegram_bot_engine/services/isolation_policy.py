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
    """Return the binding isolation decision for this process.

    Priority:
    1. Explicit TBE_REQUIRE_DOCKER / TBE_ALLOW_LOCAL_PROCESS
    2. Multi-tenant or non-dev → Docker required, local denied
    3. Dev + not multi-tenant → local may be allowed
    """
    multi = is_multi_tenant()
    dev = is_dev_environment()

    if "TBE_REQUIRE_DOCKER" in os.environ:
        require = _flag("TBE_REQUIRE_DOCKER", "1")
    else:
        # Fail closed unless pure local dev
        require = not (dev and not multi)

    if "TBE_ALLOW_LOCAL_PROCESS" in os.environ:
        allow = _flag("TBE_ALLOW_LOCAL_PROCESS", "0")
    else:
        allow = bool(dev and not multi and not require)

    # Never allow local when require_docker is on
    if require:
        allow = False

    # Multi-tenant never allows local regardless of confusing env combos
    if multi and allow:
        allow = False
        require = True

    reason = (
        f"env={environment_name() or 'unset'} multi_tenant={multi} "
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
    """Docker only. Local process is never selected (production-grade isolation).

    If Docker is unavailable the call fails closed — no host-process fallback.
    Emergency local execution requires TBE_UNSAFE_ALLOW_HOST_PROCESS=1 AND
    TBE_FORCE_LOCAL_PROCESS=1 AND non-production; still gated by assert_local_process_allowed.
    """
    from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
        DockerProcessDriver,
        docker_available,
    )

    decision = decide_isolation()
    if docker_available():
        return DockerProcessDriver(), decision
    # Fail closed — never return LocalProcessDriver from the production selector.
    raise RuntimeError(
        "docker_required_but_unavailable: isolated container required; "
        "host-process fallback removed. "
        f"({decision.reason})"
    )


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
