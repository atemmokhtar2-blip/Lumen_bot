"""Hosting service — long-running bot process management (owner-only foundation)."""

from .service import HostingService, HostInstance, HostResult, get_hosting_service

__all__ = [
    "HostingService",
    "HostInstance",
    "HostResult",
    "get_hosting_service",
]
