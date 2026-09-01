"""Hosting service — long-running bot process management (owner-only foundation).

PERMANENT_HOST plane only. Trial/preview is LiveRunner (TRIAL_CHAT).
Machine-readable contract: ``lumen.engine.services.hosting.contract``.
"""

from .service import HostingService, HostInstance, HostResult, get_hosting_service
from . import contract as hosting_contract

__all__ = [
    "HostingService",
    "HostInstance",
    "HostResult",
    "get_hosting_service",
    "hosting_contract",
]
