"""Append-only security event log — runtime attack/anomaly visibility.

World-class ops need more than CI scanners: every auth failure, admin probe,
privilege rejection, and credits anomaly should be observable.

Storage: JSONL under OUTPUT_DIR/platform/security_events/YYYYMMDD.jsonl
Env:
  SECURITY_EVENTS_ENABLED=1 (default on)
  SECURITY_EVENTS_DIR= override path
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("lumen.platform.security_events")
_lock = threading.Lock()


@dataclass
class SecurityEvent:
    event_type: str
    severity: str = "warning"  # info | warning | critical
    actor: str = ""
    tenant_id: str = ""
    ip: str = ""
    path: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))


def _enabled() -> bool:
    raw = (os.getenv("SECURITY_EVENTS_ENABLED") or "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _dir() -> Path:
    override = (os.getenv("SECURITY_EVENTS_DIR") or "").strip()
    if override:
        p = Path(override)
    else:
        try:
            from lumen.platform.paths import default_output_dir
            root = Path(default_output_dir())
        except Exception:
            root = Path(os.getenv("OUTPUT_DIR") or (Path.home() / ".lumen"))
        p = root / "platform" / "security_events"
    p.mkdir(parents=True, exist_ok=True)
    return p


def emit(
    event_type: str,
    *,
    severity: str = "warning",
    actor: str = "",
    tenant_id: str = "",
    ip: str = "",
    path: str = "",
    detail: Optional[dict[str, Any]] = None,
) -> None:
    if not _enabled():
        return
    ev = SecurityEvent(
        event_type=str(event_type),
        severity=str(severity or "warning"),
        actor=str(actor or "")[:200],
        tenant_id=str(tenant_id or "")[:120],
        ip=str(ip or "")[:80],
        path=str(path or "")[:300],
        detail=dict(detail or {}),
    )
    try:
        day = time.strftime("%Y%m%d", time.gmtime(ev.ts))
        target = _dir() / f"{day}.jsonl"
        line = ev.to_json() + "\n"
        with _lock:
            with target.open("a", encoding="utf-8") as f:
                f.write(line)
        if severity == "critical":
            logger.critical("security_event %s %s", event_type, ev.detail)
        else:
            logger.info("security_event type=%s severity=%s tenant=%s", event_type, severity, tenant_id)
    except Exception:
        logger.exception("security_event_emit_failed type=%s", event_type)


def client_ip(request: Any) -> str:
    try:
        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if xff:
            return xff
        peer = request.remote
        return str(peer or "")
    except Exception:
        return ""
