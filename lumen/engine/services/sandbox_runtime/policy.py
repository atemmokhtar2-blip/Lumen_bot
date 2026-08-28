"""Platform-grade sandbox policy — fail closed, multi-tenant PaaS posture.

Non-negotiables:
  - Never run generated bots on the host PID namespace
  - Never mount docker.sock into a bot container
  - Never use default bridge network
  - Egress allowlisted (Telegram API + optional operator list)
  - Capabilities: drop ALL; no privileged; no new privileges
  - Prefer user-kernel (gVisor) or microVM (Firecracker) when available
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import FrozenSet, Tuple


def _flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


_DEFAULT_EGRESS_HOSTS: Tuple[str, ...] = (
    "api.telegram.org",
    "core.telegram.org",
)


@dataclass(frozen=True)
class HardSandboxPolicy:
    require_isolation: bool = True
    allow_host_process: bool = False
    allow_docker_sock_in_bot: bool = False
    allow_default_bridge: bool = False
    require_egress_allowlist: bool = True
    prefer_gvisor: bool = True
    prefer_firecracker: bool = True
    max_memory: str = "192m"
    max_cpus: str = "0.4"
    max_pids: int = 48
    max_lifetime_sec: int = 0
    egress_hosts: FrozenSet[str] = field(default_factory=lambda: frozenset(_DEFAULT_EGRESS_HOSTS))


def load_policy() -> HardSandboxPolicy:
    extra = (os.environ.get("TBE_EGRESS_ALLOW_HOSTS") or "").strip()
    hosts = set(_DEFAULT_EGRESS_HOSTS)
    if extra:
        for h in extra.split(","):
            h = h.strip().lower()
            if h:
                hosts.add(h)
    return HardSandboxPolicy(
        require_isolation=not _flag("TBE_UNSAFE_ALLOW_HOST_PROCESS", "0"),
        allow_host_process=_flag("TBE_UNSAFE_ALLOW_HOST_PROCESS", "0"),
        allow_docker_sock_in_bot=False,
        allow_default_bridge=False,
        require_egress_allowlist=_flag("TBE_EGRESS_ALLOWLIST", "1"),
        prefer_gvisor=_flag("TBE_PREFER_GVISOR", "0"),
        prefer_firecracker=_flag("TBE_PREFER_FIRECRACKER", "1"),
        max_memory=(os.environ.get("TBE_DOCKER_MEMORY") or "192m").strip() or "192m",
        max_cpus=(os.environ.get("TBE_DOCKER_CPUS") or "0.4").strip() or "0.4",
        max_pids=int((os.environ.get("TBE_DOCKER_PIDS") or "48").strip() or "48"),
        max_lifetime_sec=int((os.environ.get("TBE_BOT_MAX_LIFETIME_SEC") or "0").strip() or "0"),
        egress_hosts=frozenset(hosts),
    )


def assert_no_docker_sock_mount(mount_args: list[str]) -> None:
    joined = " ".join(mount_args).lower()
    if "docker.sock" in joined:
        raise RuntimeError("policy_violation: docker.sock mount into bot container is forbidden")


def assert_network_not_default_bridge(network: str) -> None:
    n = (network or "").strip().lower()
    if not n or n in {"bridge", "default", "host", "none"}:
        raise RuntimeError(
            f"policy_violation: network={network!r} forbidden — use dedicated egress network"
        )
