"""PERMANENT_HOST plane contract — frozen from code (Phase 0).

Layers:
  1) This module — frozen field lists, gate order, security invariants.
  2) lumen.engine.schemas.hosting_contract.HostInstanceRecord — Pydantic
     validation at the trust boundary (DB/API dict → HostInstance).
  3) HostingService._inst_from_row — always loads through HostInstanceRecord.
  4) tests/test_hosting_contract_phase0.py — must stay green.

Aligned with HostInstance, market_gate, isolation_policy, sandbox select,
and live_runner (TRIAL_CHAT only).
"""
from __future__ import annotations

from typing import Final, FrozenSet, Tuple

# ── Planes (hard separation) ───────────────────────────────────────────────

PLANE_TRIAL_CHAT: Final[str] = "TRIAL_CHAT"
PLANE_PERMANENT_HOST: Final[str] = "PERMANENT_HOST"

PLANE_MODULES: Final[dict[str, str]] = {
    PLANE_TRIAL_CHAT: "lumen.engine.services.live_runner",
    PLANE_PERMANENT_HOST: "lumen.engine.services.hosting",
}

# ── HostInstance fields (must match service.HostInstance dataclass order) ─

HOST_INSTANCE_FIELDS: Final[Tuple[str, ...]] = (
    "instance_id",
    "user_id",
    "project_path",
    "entry_point",
    "bot_username",
    "status",
    "deployment_id",
    "sandbox_backend",
    "pid",
    "started_at",
    "last_error",
    "last_diagnosis",
    "token_fp",
    "public_base_url",
    "version_ref",
    "last_health_at",
)

HOST_RESULT_FIELDS: Final[Tuple[str, ...]] = (
    "ok",
    "message",
    "instance",
    "error_contract",
    "details",
)

# Status values used by HostInstance / SandboxHandle (product surface)
HOST_STATUS_VALUES: Final[FrozenSet[str]] = frozenset(
    {"starting", "running", "stopped", "failed", "unknown"}
)

# Production-allowed backend on the commercial track
PRODUCTION_BACKEND: Final[str] = "firecracker"

# Dev-only backends (never commercial sale track)
DEV_ONLY_BACKENDS: Final[FrozenSet[str]] = frozenset({"gvisor", "dind", "docker"})

ALL_KNOWN_BACKENDS: Final[FrozenSet[str]] = frozenset(
    {PRODUCTION_BACKEND} | set(DEV_ONLY_BACKENDS)
)

# HostingService public lifecycle operations
HOSTING_LIFECYCLE_METHODS: Final[Tuple[str, ...]] = (
    "start",
    "stop",
    "status",
    "logs",
    "diagnose",
    "list_for_user",
    "get",
)

# Ordered gates on HostingService.start (documentation of control flow)
# Names are stable identifiers for tests and later phases — not env vars.
START_GATE_ORDER: Final[Tuple[str, ...]] = (
    "project_path_exists",
    "user_sandbox_containment",
    "disk_quota",
    "isolation_strong_sandbox",
    "production_database_url",
    "docker_network_if_non_fc",
    "market_gate",
    "scale_queue_or_direct_sandbox",
    "firecracker_bot_health_if_applicable",
)

# Market-gate requirement keys (must remain enforceable in market_gate.py)
MARKET_GATE_REQUIREMENTS: Final[Tuple[str, ...]] = (
    "TBE_TOKEN_SECRET_MIN_32",
    "TBE_SCALE_MODE",
    "TBE_DATABASE_URL_POSTGRES",
    "TBE_ALLOW_LOCAL_PROCESS_OFF",
    "TBE_SANDBOX_BACKEND_NOT_DEV_ONLY",
    "FIRECRACKER_BIN",
    "JAILER_WHEN_REQUIRED",
    "TBE_FC_KERNEL",
    "TBE_FC_ROOTFS",
    "FC_NETWORK_OR_AUTO",
    "TBE_FC_TOKEN_IN_BOOTARGS_OFF",
)

# Security invariants — later phases must not violate these
SECURITY_INVARIANTS: Final[Tuple[str, ...]] = (
    "never_store_raw_bot_token_use_token_fp_only",
    "project_path_must_be_under_user_sandbox",
    "production_multi_tenant_firecracker_only",
    "sqlite_host_state_forbidden_outside_dev",
    "market_gate_refuses_weak_commercial_hosting",
    "no_local_process_on_commercial_track",
)

# Known product gaps frozen at Phase 0 (to be closed in later phases)
PHASE0_KNOWN_GAPS: Final[Tuple[str, ...]] = (
    "host_instance_has_no_first_class_platform_field",
    "webhook_registration_not_yet_wired_to_public_base_url",
    "multi_platform_egress_policy_not_unified",
)


def assert_host_instance_fields_match(actual_field_names: Tuple[str, ...] | list[str]) -> None:
    """Raise AssertionError if dataclass fields drift from this contract."""
    actual = tuple(actual_field_names)
    if actual != HOST_INSTANCE_FIELDS:
        raise AssertionError(
            "HostInstance fields drifted from hosting.contract.HOST_INSTANCE_FIELDS\n"
            f"  contract: {HOST_INSTANCE_FIELDS}\n"
            f"  actual:   {actual}"
        )


def token_fingerprint(raw_token: str) -> str:
    """Canonical token_fp algorithm used by HostingService (sha256 hex[:16])."""
    import hashlib

    norm = (raw_token or "").strip()
    if not norm:
        return ""
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


__all__ = [
    "PLANE_TRIAL_CHAT",
    "PLANE_PERMANENT_HOST",
    "PLANE_MODULES",
    "HOST_INSTANCE_FIELDS",
    "HOST_RESULT_FIELDS",
    "HOST_STATUS_VALUES",
    "PRODUCTION_BACKEND",
    "DEV_ONLY_BACKENDS",
    "ALL_KNOWN_BACKENDS",
    "HOSTING_LIFECYCLE_METHODS",
    "START_GATE_ORDER",
    "MARKET_GATE_REQUIREMENTS",
    "SECURITY_INVARIANTS",
    "PHASE0_KNOWN_GAPS",
    "assert_host_instance_fields_match",
    "token_fingerprint",
]
