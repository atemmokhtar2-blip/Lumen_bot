"""Emit host heartbeats into usage_batches (phase 2 — no debit)."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def emit_host_heartbeat(
    *,
    tenant_id: str,
    bot_id: str,
    uptime_seconds: int = 0,
    ram_mb: int = 0,
    messages_processed: int = 0,
    llm_tokens_used: int = 0,
    window_seconds: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Record a metrics batch for a running bot. Never touches CreditService."""
    if not tenant_id or not bot_id:
        return {"ok": False, "error": "tenant_or_bot_missing"}
    if (os.getenv("TBE_USAGE_HEARTBEAT") or "1").strip().lower() in {"0", "false", "off", "no"}:
        return {"ok": False, "error": "heartbeat_disabled"}
    win = int(window_seconds or os.getenv("TBE_USAGE_HEARTBEAT_SEC") or "300")
    now = time.time()
    start = now - max(1, win)
    # Stable idempotency per bot per window bucket
    bucket = int(now // win)
    key = f"hb-{bot_id}-{bucket}"
    body = {
        "bot_id": str(bot_id)[:120],
        "window_start": start,
        "window_end": now,
        "messages_processed": int(messages_processed),
        "llm_tokens_used": int(llm_tokens_used),
        "uptime_seconds": int(uptime_seconds),
        "ram_mb": int(ram_mb),
        "idempotency_key": key[:200],
        "metadata": dict(metadata or {}),
    }
    try:
        from b2b_platform.usage_batches import get_usage_batch_service

        result = get_usage_batch_service().ingest(str(tenant_id), body, source="supervisor")
        return {
            "ok": result.ok,
            "replay": result.replay,
            "reason": result.reason,
            "batch_id": result.batch.batch_id if result.batch else "",
        }
    except Exception as exc:
        logger.warning("emit_host_heartbeat failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}
