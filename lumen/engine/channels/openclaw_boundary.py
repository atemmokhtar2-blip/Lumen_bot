"""OpenClaw boundary — multi-channel delivery contract (Phase 4).

This is NOT a builder. It maps a delivered bot artifact to channel ops.
Wire real OpenClaw later via OPENCLAW_URL; until then status is stub.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChannelMessage:
    channel: str  # telegram | discord | slack | …
    user_ref: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class OpenClawBoundary:
    def __init__(self) -> None:
        self.base = (os.getenv("OPENCLAW_URL") or "").rstrip("/")
        self.token = (os.getenv("OPENCLAW_TOKEN") or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.base)

    def publish_bot_package(
        self,
        *,
        channel: str,
        package_path: str,
        caption: str = "",
    ) -> dict[str, Any]:
        if not self.configured:
            return {
                "ok": False,
                "error": "OPENCLAW_URL not set",
                "hint": "Channels stay on native Telegram until OpenClaw is wired",
            }
        payload = {
            "channel": channel,
            "package_path": package_path,
            "caption": caption,
        }
        url = f"{self.base}/v1/publish"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    body = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    body = {"raw": raw[:2000]}
                return {"ok": True, "status": getattr(resp, "status", 200), "data": body}
        except Exception as exc:
            logger.warning("OpenClaw publish failed: %s", exc)
            return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def channel_status() -> dict[str, Any]:
    b = OpenClawBoundary()
    return {
        "openclaw_configured": b.configured,
        "native_telegram": True,
        "note": "Build engine is independent of channels",
    }


__all__ = ["ChannelMessage", "OpenClawBoundary", "channel_status"]
