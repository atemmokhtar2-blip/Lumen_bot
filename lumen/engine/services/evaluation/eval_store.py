"""Append-only JSONL evaluation store (production-friendly, no mock DB)."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from .run_record import EvalRunRecord

_LOCK = threading.Lock()


def _default_path() -> Path:
    base = Path(os.environ.get("LUMEN_EVAL_DIR") or os.environ.get("OUTPUT_DIR") or (Path.home() / ".lumen"))
    path = base / "eval" / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_eval_record(rec: EvalRunRecord | dict[str, Any], *, path: Path | None = None) -> Path:
    target = path or _default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = rec.to_dict() if isinstance(rec, EvalRunRecord) else dict(rec)
    line = json.dumps(payload, ensure_ascii=False)
    with _LOCK:
        with target.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return target


def load_eval_records(*, path: Path | None = None, limit: int = 500) -> list[dict[str, Any]]:
    target = path or _default_path()
    if not target.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with target.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-max(1, min(limit, 5000)) :]


def summarize_evals(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = records if records is not None else load_eval_records()
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "success_rate": 0.0,
            "avg_attempts": 0.0,
            "avg_latency_s": 0.0,
            "avg_cost_usd": 0.0,
            "by_platform": {},
        }
    ok = sum(1 for r in rows if r.get("success"))
    attempts = [float(r.get("attempts") or 0) for r in rows]
    latency = [float(r.get("latency_s") or 0) for r in rows]
    cost = [float(r.get("cost_usd") or 0) for r in rows]
    by: dict[str, dict[str, float]] = {}
    for r in rows:
        p = str(r.get("platform") or "unknown")
        bucket = by.setdefault(p, {"n": 0, "ok": 0})
        bucket["n"] += 1
        if r.get("success"):
            bucket["ok"] += 1
    by_platform = {
        p: {
            "n": int(v["n"]),
            "success_rate": round(v["ok"] / max(1, v["n"]), 4),
        }
        for p, v in by.items()
    }
    return {
        "n": n,
        "success_rate": round(ok / n, 4),
        "avg_attempts": round(sum(attempts) / n, 4),
        "avg_latency_s": round(sum(latency) / n, 4),
        "avg_cost_usd": round(sum(cost) / n, 6),
        "by_platform": by_platform,
    }


__all__ = ["append_eval_record", "load_eval_records", "summarize_evals"]
