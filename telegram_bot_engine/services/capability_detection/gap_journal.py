"""Gap Journal — durable log of capability gaps (Phase 4 foundation).

Records what users asked for that the registry could not fully satisfy.
Future Dynamic Tool Builder / Web Research reads this journal.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GapRecord:
    phrase: str
    reason: str
    request_preview: str = ""
    suggested_keys: list[str] = field(default_factory=list)
    status: str = "open"  # open | researching | resolved | ignored
    count: int = 1
    first_seen: float = 0.0
    last_seen: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


_LOCK = threading.Lock()
_CACHE: dict[str, GapRecord] = {}
_LOADED = False


def _journal_path() -> Path:
    base = os.getenv("OUTPUT_DIR") or "/tmp/generated"
    p = Path(base) / "platform" / "gap_journal.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _key(phrase: str, reason: str) -> str:
    return f"{(phrase or '').strip().lower()}::{(reason or '').strip()[:80]}"


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    path = _journal_path()
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                rec = GapRecord(
                    phrase=str(data.get("phrase") or ""),
                    reason=str(data.get("reason") or ""),
                    request_preview=str(data.get("request_preview") or ""),
                    suggested_keys=list(data.get("suggested_keys") or []),
                    status=str(data.get("status") or "open"),
                    count=int(data.get("count") or 1),
                    first_seen=float(data.get("first_seen") or 0),
                    last_seen=float(data.get("last_seen") or 0),
                    meta=dict(data.get("meta") or {}),
                )
                _CACHE[_key(rec.phrase, rec.reason)] = rec
        except Exception:
            pass
    _LOADED = True


def _append(rec: GapRecord) -> None:
    path = _journal_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")


def record_gaps(
    *,
    request: str,
    gaps: list[Any],
    detection_status: str = "",
) -> list[GapRecord]:
    """Upsert gap entries from a DetectionReport.gaps list."""
    with _LOCK:
        _load()
        now = time.time()
        out: list[GapRecord] = []
        for g in gaps or []:
            phrase = str(getattr(g, "phrase", None) or (g.get("phrase") if isinstance(g, dict) else "") or "")
            reason = str(getattr(g, "reason", None) or (g.get("reason") if isinstance(g, dict) else "") or "")
            suggested = list(
                getattr(g, "suggested_keys", None)
                or (g.get("suggested_keys") if isinstance(g, dict) else None)
                or []
            )
            if not phrase and not reason:
                continue
            k = _key(phrase, reason)
            if k in _CACHE:
                rec = _CACHE[k]
                rec.count += 1
                rec.last_seen = now
                if request and len(request) > len(rec.request_preview):
                    rec.request_preview = (request or "")[:300]
            else:
                rec = GapRecord(
                    phrase=phrase,
                    reason=reason,
                    request_preview=(request or "")[:300],
                    suggested_keys=suggested[:8],
                    status="open",
                    count=1,
                    first_seen=now,
                    last_seen=now,
                    meta={"detection_status": detection_status},
                )
                _CACHE[k] = rec
            _append(rec)
            out.append(rec)
        return out


def list_open_gaps(*, limit: int = 50) -> list[GapRecord]:
    with _LOCK:
        _load()
        items = [r for r in _CACHE.values() if r.status == "open"]
        items.sort(key=lambda r: (-r.count, -r.last_seen))
        return items[: max(1, int(limit))]


def mark_gap_status(phrase: str, reason: str, status: str) -> bool:
    with _LOCK:
        _load()
        k = _key(phrase, reason)
        rec = _CACHE.get(k)
        if not rec:
            return False
        rec.status = status
        _append(rec)
        return True


def journal_stats() -> dict[str, Any]:
    with _LOCK:
        _load()
        open_n = sum(1 for r in _CACHE.values() if r.status == "open")
        return {
            "total": len(_CACHE),
            "open": open_n,
            "path": str(_journal_path()),
        }


__all__ = [
    "GapRecord",
    "record_gaps",
    "list_open_gaps",
    "mark_gap_status",
    "journal_stats",
]
