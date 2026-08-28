"""Central isolation policy for running untrusted generated bot code.

All entry points that execute user/tenant code MUST consult this module.

Policy (production multi-tenant):
  1) Strong sandbox required: Firecracker (best) > gVisor > DinD > hardened Docker.
  2) LocalProcess is forbidden unless explicit dual gate or allowed dev fallback.
  3) Docker is one backend among sandbox_runtime — not the only isolation form.
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
    """require_docker kept for backward callers; prefer require_strong_isolation."""

    require_docker: bool
    allow_local: bool
    reason: str
    require_strong_isolation: bool = True

    @property
    def may_use_local(self) -> bool:
        return self.allow_local


def strong_sandbox_available() -> tuple[bool, str]:
    """True if any sandbox_runtime backend can run right now."""
    try:
        from lumen.engine.services.sandbox_runtime import probe_all

        probes = probe_all()
        for p in probes:
            if p.available:
                return True, f"{p.name}:{p.reason}"
        reasons = "; ".join(f"{p.name}:{p.reason}" for p in probes) or "no_probes"
        return False, reasons
    except Exception as exc:
        return False, f"probe_error:{type(exc).__name__}"


def decide_isolation() -> IsolationDecision:
    """Strong sandbox required in multi-tenant/production; local only with explicit gates.

    Production / multi-tenant: TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER is **ignored**.
    Host LocalProcess is allowed only via dual gate:
      TBE_ALLOW_LOCAL_PROCESS=1 AND TBE_FORCE_LOCAL_PROCESS=1
    (intentional single-tenant debug — never the API default).
    """
    multi = is_multi_tenant()
    dev = is_dev_environment()
    dual = _flag("TBE_ALLOW_LOCAL_PROCESS", "0") and _flag("TBE_FORCE_LOCAL_PROCESS", "0")

    if dual:
        return IsolationDecision(
            require_docker=False,
            allow_local=True,
            require_strong_isolation=False,
            reason=f"explicit_local multi_tenant={multi} dev={dev}",
        )

    # Multi-tenant or non-dev: never allow host-local fallback (fail-closed).
    if multi or not dev:
        fallback = False
    else:
        # Dev-only convenience when Docker is missing on a developer laptop.
        fallback = _flag("TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER", "1")

    return IsolationDecision(
        require_docker=True,  # legacy: try container backends in the stack
        allow_local=fallback,
        require_strong_isolation=True,
        reason=(
            f"strong_sandbox_required local_fallback={fallback} "
            f"multi_tenant={multi} dev={dev}"
        ),
    )


def assert_local_process_allowed() -> None:
    """Raise if LocalProcessDriver must not run under current policy."""
    d = decide_isolation()
    if not d.allow_local:
        raise RuntimeError(
            "local_process_denied: production/multi-tenant forbids host LocalProcess; "
            "dev may use TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER=1; explicit dual gate "
            "TBE_ALLOW_LOCAL_PROCESS=1 + TBE_FORCE_LOCAL_PROCESS=1 only when intentional. "
            f"({d.reason})"
        )


def select_process_driver():
    """Prefer SandboxProcessDriver (FC/gVisor/DinD/Docker). Local only if explicitly allowed.

    Production multi-tenant must never receive LocalProcessDriver.
    """
    decision = decide_isolation()
    if decision.require_strong_isolation:
        try:
            from lumen.engine.engines.generators.live_deployment.sandbox_process_driver import (
                SandboxProcessDriver,
            )
            require_strong_isolation()
            return SandboxProcessDriver(), decision
        except Exception as exc:
            raise RuntimeError(
                "sandbox_required_but_unavailable: isolated runtime required; "
                f"({decision.reason}; {type(exc).__name__}:{exc})"
            ) from exc

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
    """Legacy name: require *some* strong sandbox, not Docker exclusively."""
    d = decide_isolation()
    if not d.require_strong_isolation and d.allow_local:
        return
    ok, reason = strong_sandbox_available()
    if ok:
        return
    # Fall back to docker-only check for older callers
    try:
        from lumen.engine.engines.generators.live_deployment.docker_process_driver import (
            docker_available,
        )

        if docker_available():
            return
    except Exception:
        pass
    raise RuntimeError(
        "strong_sandbox_required_but_unavailable: "
        f"({d.reason}; probes={reason})"
    )


def require_strong_isolation() -> None:
    """Fail closed if no Firecracker/gVisor/DinD/Docker backend is available."""
    d = decide_isolation()
    if d.allow_local and not d.require_strong_isolation:
        return
    ok, reason = strong_sandbox_available()
    if not ok:
        raise RuntimeError(
            "strong_sandbox_required_but_unavailable: "
            f"({d.reason}; probes={reason})"
        )


__all__ = [
    "IsolationDecision",
    "decide_isolation",
    "assert_local_process_allowed",
    "select_process_driver",
    "require_docker_runtime",
    "require_strong_isolation",
    "strong_sandbox_available",
    "is_dev_environment",
    "is_multi_tenant",
    "environment_name",
]
