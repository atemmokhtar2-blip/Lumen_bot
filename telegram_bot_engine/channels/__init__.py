"""Channel layer — delivery surfaces only (not the build engine).

OpenClaw / Telegram / Discord adapters belong here.
Generation stays in engine_router + catalog/cline.
"""
from __future__ import annotations

from .openclaw_boundary import ChannelMessage, OpenClawBoundary, channel_status

__all__ = ["ChannelMessage", "OpenClawBoundary", "channel_status"]
