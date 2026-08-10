"""Usage metering — generations, API calls, host-minutes."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class UsageBucket:
    tenant_id: str
    period: str  # YYYY-MM
    generations: int = 0
    api_calls: int = 0
    host_starts: int = 0
    host_minutes: float = 0.0
    bytes_out: int = 0
    extra: dict[str, int] = field(default_factory=dict)


class MeteringService:
    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root or os.getenv("OUTPUT_DIR", "/tmp/generated"))
        self.root = base / "platform" / "metering"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._rpm: dict[str, list[float]] = defaultdict(list)  # tenant -> timestamps

    def _period(self) -> str:
        return time.strftime("%Y-%m", time.gmtime())

    def _path(self, tenant_id: str, period: str | None = None) -> Path:
        return self.root / f"{tenant_id}_{period or self._period()}.json"

    def _load(self, tenant_id: str, period: str | None = None) -> UsageBucket:
        path = self._path(tenant_id, period)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return UsageBucket(**{k: v for k, v in data.items() if k in UsageBucket.__dataclass_fields__})
            except Exception:
                pass
        return UsageBucket(tenant_id=tenant_id, period=period or self._period())

    def _save(self, bucket: UsageBucket) -> None:
        path = self._path(bucket.tenant_id, bucket.period)
        path.write_text(
            json.dumps(bucket.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(
        self,
        tenant_id: str,
        *,
        generations: int = 0,
        api_calls: int = 0,
        host_starts: int = 0,
        host_minutes: float = 0.0,
        bytes_out: int = 0,
        event: str = "",
    ) -> UsageBucket:
        with self._lock:
            b = self._load(tenant_id)
            b.generations += int(generations)
            b.api_calls += int(api_calls)
            b.host_starts += int(host_starts)
            b.host_minutes += float(host_minutes)
            b.bytes_out += int(bytes_out)
            if event:
                b.extra[event] = int(b.extra.get(event, 0)) + 1
            self._save(b)
            return b

    def snapshot(self, tenant_id: str) -> dict[str, Any]:
        b = self._load(tenant_id)
        return dict(b.__dict__)

    def check_rpm(self, tenant_id: str, limit: int) -> bool:
        """Return True if under rate limit."""
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._rpm[tenant_id]
            while hits and now - hits[0] > 60.0:
                hits.pop(0)
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


_METER: MeteringService | None = None


def get_metering() -> MeteringService:
    global _METER
    if _METER is None:
        _METER = MeteringService()
    return _METER
