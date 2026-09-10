"""Production fail-closed hardening — refuse unsafe env combinations."""
from __future__ import annotations

import os


def is_production() -> bool:
    env = (
        os.environ.get("ENVIRONMENT")
        or os.environ.get("TBE_ENV")
        or os.environ.get("LUMEN_ENV")
        or ""
    ).strip().lower()
    return env in {"prod", "production", "staging"}


def assert_no_unsafe_sandbox_flags() -> None:
    """Raise if operator enabled lab-only escapes in production."""
    if not is_production():
        return
    forbidden = []
    for name, bad in (
        ("TBE_UNSAFE_ALLOW_HOST_PROCESS", "1"),
        ("TBE_FC_ALLOW_NO_NET", "1"),
        ("TBE_FC_ALLOW_SHARED_TAP", "1"),
        ("TBE_DOCKER_ALLOW_NO_SECCOMP", "1"),
        ("TBE_MARKET_GATE", "0"),
        ("TBE_EGRESS_ALLOWLIST", "0"),
        ("TBE_EGRESS_STRICT", "0"),
        ("TBE_FC_EGRESS_STRICT", "0"),
        ("TBE_ALLOW_WEAK_SANDBOX", "1"),
    ):
        raw = (os.environ.get(name) or "").strip().lower()
        if bad == "0":
            if raw in {"0", "false", "no", "off"}:
                forbidden.append(f"{name}={raw}")
        else:
            if raw in {"1", "true", "yes", "on"}:
                forbidden.append(f"{name}={raw}")
    pref = (os.environ.get("TBE_SANDBOX_BACKEND") or "").strip().lower()
    if pref in {"docker", "dind", "gvisor"}:
        forbidden.append(f"TBE_SANDBOX_BACKEND={pref}")
    if forbidden:
        raise RuntimeError(
            "production_unsafe_sandbox_flags:" + ",".join(forbidden)
        )


def assert_firecracker_only_for_hosting() -> None:
    """Commercial hosting: Firecracker default; isolated docker only with dual-ACK."""
    if not is_production():
        return
    pref = (os.environ.get("TBE_SANDBOX_BACKEND") or "auto").strip().lower()
    if pref in {"gvisor", "dind"}:
        raise RuntimeError(f"production_hosting_rejects_backend: backend={pref}")
    if pref == "docker":
        ack = (os.environ.get("TBE_DOCKER_ISOLATION_ACK") or "").strip()
        if ack != "I_ACCEPT_ISOLATED_DOCKER_NOT_FIRECRACKER":
            raise RuntimeError(
                "production_hosting_requires_firecracker_or_docker_isolation_ack"
            )


__all__ = [
    "is_production",
    "assert_no_unsafe_sandbox_flags",
    "assert_firecracker_only_for_hosting",
]
