"""Platform generators — Telegram / Discord / WhatsApp / web scaffolds.

Product scope: all bot platforms + path toward apps/sites (not Telegram-only).
"""
from __future__ import annotations

from .registry import (
    detect_platform,
    apply_platform_scaffold,
    supported_platforms,
)

__all__ = [
    "detect_platform",
    "apply_platform_scaffold",
    "supported_platforms",
]
