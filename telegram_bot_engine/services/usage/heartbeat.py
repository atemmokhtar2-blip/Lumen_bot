"""Host heartbeats → usage_batches (phase 2, no debit).

Collects docker stats when possible; registers bot ownership; content-hashed batches.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _docker_stats(container_id: str) -> dict[str, int]:
    """Best-effort RAM/CPU from `docker stats --no-stream`."""
    out: dict[str, int] = {"ram_mb": 0, "cpu_millicores": 0, "uptime_seconds": 0}
    if not container_id:
        return out
    try:
        p = subprocess.run(
            [
                "docker", "stats", container_id, "--no-stream",
                "--format", "{{.MemUsage}}\t{{.CPUPerc}}",
            ],
            capture_output=True, text=True, timeout=8, check=False,
        )
        if p.returncode != 0:
            return out
        line = (p.stdout or "").strip().splitlines()
        if not line:
            return out
        parts = line[0].split("\t")
        mem = (parts[0] if parts else "").split("/")[0].strip()
        # e.g. 128.5MiB or 1.2GiB
        ram_mb = 0
        try:
            if mem.lower().endswith("gib"):
                ram_mb = int(float(mem[:-3]) * 1024)
            elif mem.lower().endswith("mib"):
                ram_mb = int(float(mem[:-3]))
            elif mem.lower().endswith("mb"):
                ram_mb = int(float(mem[:-2]))
        except Exception:
            ram_mb = 0
        cpu_m = 0
        try:
            cpu_s = (parts[1] if len(parts) > 1 else "0").replace("%", "").strip()
            cpu_m = int(float(cpu_s) * 10)  # % → millicores approx on 1 CPU
        except Exception:
            cpu_m = 0
        out["ram_mb"] = max(0, ram_mb)
        out["cpu_millicores"] = max(0, cpu_m)
    except Exception as exc:
        logger.debug("docker_stats failed: %s", type(exc).__name__)
    try:
        p2 = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.StartedAt}}", container_id],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if p2.returncode == 0 and p2.stdout.strip():
            p3 = subprocess.run(
                ["date", "-d", p2.stdout.strip(), "+%s"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            if p3.returncode == 0:
                started = int(p3.stdout.strip())
                out["uptime_seconds"] = max(0, int(time.time()) - started)
    except Exception:
        pass
    return out


def emit_host_heartbeat(
    *,
    tenant_id: str,
    bot_id: str,
    container_id: str = "",
    uptime_seconds: int = 0,
    ram_mb: int = 0,
    messages_processed: int = 0,
    llm_tokens_used: int = 0,
    cpu_millicores: int = 0,
    window_seconds: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
    register: bool = True,
) -> dict[str, Any]:
    if not tenant_id or not bot_id:
        return {"ok": False, "error": "tenant_or_bot_missing"}
    if (os.getenv("TBE_USAGE_HEARTBEAT") or "1").strip().lower() in {"0", "false", "off", "no"}:
        return {"ok": False, "error": "heartbeat_disabled"}

    if register:
        try:
            from b2b_platform.usage_batches import register_bot
            register_bot(str(tenant_id), str(bot_id))
        except Exception:
            pass

    stats = _docker_stats(container_id) if container_id else {}
    if not ram_mb:
        ram_mb = int(stats.get("ram_mb") or 0)
    if not cpu_millicores:
        cpu_millicores = int(stats.get("cpu_millicores") or 0)
    if not uptime_seconds:
        uptime_seconds = int(stats.get("uptime_seconds") or 0)

    win = int(window_seconds or os.getenv("TBE_USAGE_HEARTBEAT_SEC") or "300")
    now = time.time()
    start = now - max(1, win)
    bucket = int(now // win)
    key = f"hb-{bot_id}-{bucket}"[:200]
    body = {
        "bot_id": str(bot_id)[:120],
        "window_start": start,
        "window_end": now,
        "messages_processed": int(messages_processed),
        "llm_tokens_used": int(llm_tokens_used),
        "uptime_seconds": int(uptime_seconds),
        "ram_mb": int(ram_mb),
        "cpu_millicores": int(cpu_millicores),
        "idempotency_key": key,
        "metadata": dict(metadata or {}, container_id=container_id[:64] if container_id else ""),
    }
    try:
        from b2b_platform.usage_batches import get_usage_batch_service
        result = get_usage_batch_service().ingest(
            str(tenant_id), body, source="supervisor", require_ownership=True, skip_rate_limit=True,
        )
        return {
            "ok": result.ok,
            "replay": result.replay,
            "reason": result.reason,
            "batch_id": result.batch.batch_id if result.batch else "",
            "content_hash": result.batch.content_hash if result.batch else "",
        }
    except Exception as exc:
        logger.warning("emit_host_heartbeat failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}
