"""Collect host instance logs from Firecracker and optionally ship to Loki.

Config:
  TBE_LOKI_URL=http://loki:3100/loki/api/v1/push
  TBE_LOG_AGGREGATE_DIR=...  # local ring buffer per instance
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("tbe.hosting.log_aggregator")


def _local_dir() -> Path:
    raw = (os.environ.get("TBE_LOG_AGGREGATE_DIR") or "").strip()
    if raw:
        p = Path(raw)
    else:
        try:
            from lumen.bot.config import OUTPUT_DIR

            p = Path(OUTPUT_DIR) / "hosting" / "logs"
        except Exception:
            p = Path.home() / ".lumen" / "hosting" / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def collect_instance_logs(instance_id: str, deployment_id: str, *, limit: int = 200) -> list[str]:
    lines: list[str] = []
    dep = (deployment_id or "").strip()
    if dep:
        try:
            from lumen.engine.services.sandbox_runtime.firecracker_backend import (
                FirecrackerSandboxBackend,
            )

            lines = list(FirecrackerSandboxBackend().logs(dep, limit=max(10, min(500, limit))) or [])
        except Exception as exc:
            lines = [f"log_collect_error:{type(exc).__name__}"]
    # persist ring
    try:
        path = _local_dir() / f"{instance_id}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            for line in lines[-limit:]:
                fh.write(json.dumps({"ts": time.time(), "line": str(line)[:2000]}, ensure_ascii=False) + "\n")
        # trim file size roughly
        if path.stat().st_size > 5_000_000:
            content = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-2000:]
            path.write_text("\n".join(content) + "\n", encoding="utf-8")
    except Exception:
        pass
    return lines


def ship_to_loki(instance_id: str, lines: list[str], *, labels: dict[str, str] | None = None) -> bool:
    url = (os.environ.get("TBE_LOKI_URL") or "").strip()
    if not url or not lines:
        return False
    lbl = {"job": "lumen-host", "instance_id": instance_id}
    if labels:
        lbl.update({k: str(v) for k, v in labels.items()})
    # Loki push API
    streams = [
        {
            "stream": lbl,
            "values": [[str(int(time.time() * 1e9)), str(line)[:4000]] for line in lines[-100:]],
        }
    ]
    body = json.dumps({"streams": streams}).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "Lumen-Host/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception as exc:
        logger.warning("loki ship failed: %s", type(exc).__name__)
        return False


def aggregate_and_ship(instance_id: str, deployment_id: str, *, limit: int = 100) -> dict[str, Any]:
    lines = collect_instance_logs(instance_id, deployment_id, limit=limit)
    shipped = ship_to_loki(instance_id, lines)
    return {"lines": len(lines), "loki": shipped}


__all__ = ["collect_instance_logs", "ship_to_loki", "aggregate_and_ship"]
