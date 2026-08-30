"""Central isolation policy for running untrusted generated bot code.

All entry points that execute user/tenant code MUST consult this module.

Policy (production multi-tenant):
  1) Firecracker microVM is the sole production sandbox (no gVisor/Docker fallback).
  2) LocalProcess is forbidden unless explicit dual gate in dev single-tenant.
  3) gVisor / DinD / Docker exist only as explicit dev backends.
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
    """True if the required sandbox can run right now.

    Production/multi-tenant: Firecracker only.
    Dev: any available backend (for local testing).
    """
    try:
        from lumen.engine.services.sandbox_runtime.select import (
            is_production_sandbox_path,
            probe_all,
        )

        probes = probe_all()
        if is_production_sandbox_path():
            for p in probes:
                if p.name == "firecracker" and p.available:
                    return True, f"{p.name}:{p.reason}"
            fc = next((p for p in probes if p.name == "firecracker"), None)
            reason = fc.reason if fc else "firecracker_not_probed"
            return False, f"firecracker_required:{reason}"
        for p in probes:
            if p.available:
                return True, f"{p.name}:{p.reason}"
        reasons = "; ".join(f"{p.name}:{p.reason}" for p in probes) or "no_probes"
        return False, reasons
    except Exception as exc:
        return False, f"probe_error:{type(exc).__name__}"


def decide_isolation() -> IsolationDecision:
    """Fail-closed: multi-tenant/production never host-local; dev single-tenant may dual-gate."""
    multi = is_multi_tenant()
    dev = is_dev_environment()
    dual = _flag("TBE_ALLOW_LOCAL_PROCESS", "0") and _flag("TBE_FORCE_LOCAL_PROCESS", "0")

    # Absolute: multi-tenant or production → strong isolation only.
    if multi or not dev:
        return IsolationDecision(
            require_docker=True,
            allow_local=False,
            require_strong_isolation=True,
            reason=f"fail_closed multi_tenant={multi} dev={dev}",
        )

    # Dev + single-tenant only below this line.
    if dual:
        return IsolationDecision(
            require_docker=False,
            allow_local=True,
            require_strong_isolation=False,
            reason="dev_single_tenant_explicit_local",
        )

    fallback = _flag("TBE_LOCAL_FALLBACK_WHEN_NO_DOCKER", "0")
    return IsolationDecision(
        require_docker=True,
        allow_local=fallback,
        require_strong_isolation=not fallback,
        reason=f"dev_single_tenant local_fallback={fallback}",
    )


def assert_local_process_allowed() -> None:
    """Raise if LocalProcessDriver must not run under current policy."""
    d = decide_isolation()
    if not d.allow_local:
        raise RuntimeError(
            f"local_process_denied: host LocalProcess forbidden ({d.reason})"
        )


def select_process_driver():
    """Prefer SandboxProcessDriver (Firecracker in production). Local only if explicitly allowed.

    Production multi-tenant must never receive LocalProcessDriver.
    """
    decision = decide_isolation()
    if decision.require_strong_isolation:
        try:
            from lumen.engine.services.live_deployment.sandbox_process_driver import (
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
        from lumen.engine.services.live_deployment.local_process_driver import (
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
        from lumen.engine.services.live_deployment.docker_process_driver import (
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
    """Fail closed if required sandbox is unavailable (Firecracker in production)."""
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
