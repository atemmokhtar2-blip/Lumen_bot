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


def collect_instance_logs(
    instance_id: str,
    deployment_id: str,
    *,
    limit: int = 200,
    project_path: str = "",
) -> list[str]:
    lines: list[str] = []
    dep = (deployment_id or "").strip()
    if dep:
        try:
            from lumen.engine.services.sandbox_runtime.firecracker_backend import (
                FirecrackerSandboxBackend,
            )

            lines = list(
                FirecrackerSandboxBackend().logs(dep, limit=max(10, min(500, limit))) or []
            )
        except Exception as exc:
            lines = ["log_collect_error:%s" % type(exc).__name__]
    root = (project_path or "").strip()
    if root:
        try:
            from pathlib import Path as _P

            plog = _P(root) / "logs" / "bot.stdout.log"
            if plog.is_file():
                tail = plog.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
                lines = list(lines) + ["[project/logs] %s" % x for x in tail]
        except Exception:
            pass
    try:
        path = _local_dir() / ("%s.jsonl" % instance_id)
        with path.open("a", encoding="utf-8") as fh:
            for line in lines[-limit:]:
                fh.write(
                    json.dumps(
                        {"ts": time.time(), "line": str(line)[:2000]}, ensure_ascii=False
                    )
                    + chr(10)
                )
        if path.stat().st_size > 5_000_000:
            content = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-2000:]
            path.write_text(chr(10).join(content) + chr(10), encoding="utf-8")
    except Exception:
        pass
    if root:
        try:
            from pathlib import Path as _P

            pl = _P(root) / "logs"
            pl.mkdir(parents=True, exist_ok=True)
            with (pl / "host.jsonl").open("a", encoding="utf-8") as fh:
                for line in lines[-min(50, max(1, limit)):]:
                    fh.write(
                        json.dumps(
                            {"ts": time.time(), "line": str(line)[:2000]},
                            ensure_ascii=False,
                        )
                        + chr(10)
                    )
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


def ship_to_elasticsearch(instance_id: str, lines: list[str]) -> bool:
    """Bulk index lines to Elasticsearch if TBE_ES_URL is set."""
    base = (os.environ.get("TBE_ES_URL") or "").strip().rstrip("/")
    if not base or not lines:
        return False
    index = (os.environ.get("TBE_ES_INDEX") or "lumen-host-logs").strip()
    # NDJSON bulk
    parts = []
    for line in lines[-100:]:
        parts.append(json.dumps({"index": {"_index": index}}))
        parts.append(json.dumps({
            "@timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "instance_id": instance_id,
            "message": str(line)[:4000],
            "job": "lumen-host",
        }, ensure_ascii=False))
    body = ("\n".join(parts) + "\n").encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{base}/_bulk",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-ndjson", "User-Agent": "Lumen-Host/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception as exc:
        logger.warning("elasticsearch ship failed: %s", type(exc).__name__)
        return False


def aggregate_and_ship(instance_id: str, deployment_id: str, *, limit: int = 100, project_path: str = "") -> dict[str, Any]:
    lines = collect_instance_logs(instance_id, deployment_id, limit=limit, project_path=project_path)
    loki = ship_to_loki(instance_id, lines)
    es = ship_to_elasticsearch(instance_id, lines)
    return {"lines": len(lines), "loki": loki, "elasticsearch": es}


def aggregate_all_running(hosting_service, *, limit: int = 80) -> dict[str, Any]:
    """Collect logs from every running instance (central aggregation pass)."""
    stats = {"instances": 0, "lines": 0, "loki": 0, "elasticsearch": 0}
    instances = getattr(hosting_service, "_instances", {}) or {}
    if not isinstance(instances, dict):
        instances = {}
    for inst in list(instances.values()):
        if (getattr(inst, "status", "") or "") != "running":
            continue
        stats["instances"] += 1
        r = aggregate_and_ship(
            str(getattr(inst, "instance_id", "")),
            str(getattr(inst, "deployment_id", "") or ""),
            limit=limit,
            project_path=str(getattr(inst, "project_path", "") or ""),
        )
        stats["lines"] += int(r.get("lines") or 0)
        stats["loki"] += 1 if r.get("loki") else 0
        stats["elasticsearch"] += 1 if r.get("elasticsearch") else 0
    return stats


__all__ = ["collect_instance_logs", "ship_to_loki", "ship_to_elasticsearch", "aggregate_and_ship", "aggregate_all_running"]
