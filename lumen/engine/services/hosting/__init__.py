"""Hosting service — long-running bot process management (owner-only foundation).

PERMANENT_HOST plane only. Trial/preview is LiveRunner (TRIAL_CHAT).
Machine-readable contract: ``lumen.engine.services.hosting.contract``.
"""

from .service import HostingService, HostInstance, HostResult, get_hosting_service
from . import contract as hosting_contract
from .host_mode import HostMode, allocate_public_url, host_mode_for_kind

__all__ = [
    "HostingService",
    "HostInstance",
    "HostResult",
    "get_hosting_service",
    "hosting_contract",
    "HostMode",
    "allocate_public_url",
    "host_mode_for_kind",
]
