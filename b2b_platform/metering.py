"""Usage metering — generations, API calls, host-minutes (process-safe)."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .filelock import atomic_write_text, exclusive_lock
from .rate_limit import get_rate_limiter


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

    def _period(self) -> str:
        return time.strftime("%Y-%m", time.gmtime())

    def _path(self, tenant_id: str, period: str | None = None) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tenant_id)[:80]
        return self.root / f"{safe}_{period or self._period()}.json"

    def _load_unlocked(self, path: Path, tenant_id: str, period: str) -> UsageBucket:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return UsageBucket(
                    **{k: v for k, v in data.items() if k in UsageBucket.__dataclass_fields__}
                )
            except Exception:
                pass
        return UsageBucket(tenant_id=tenant_id, period=period)

    def _save_unlocked(self, path: Path, bucket: UsageBucket) -> None:
        atomic_write_text(path, json.dumps(bucket.__dict__, ensure_ascii=False, indent=2))

    def snapshot(self, tenant_id: str) -> dict[str, Any]:
        period = self._period()
        path = self._path(tenant_id, period)
        with exclusive_lock(path):
            b = self._load_unlocked(path, tenant_id, period)
            return dict(b.__dict__)

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
        period = self._period()
        path = self._path(tenant_id, period)
        with exclusive_lock(path):
            b = self._load_unlocked(path, tenant_id, period)
            b.generations += int(generations)
            b.api_calls += int(api_calls)
            b.host_starts += int(host_starts)
            b.host_minutes += float(host_minutes)
            b.bytes_out += int(bytes_out)
            if event:
                b.extra[event] = int(b.extra.get(event, 0)) + 1
            self._save_unlocked(path, b)
            return b

    def try_reserve_generation(self, tenant_id: str, limit: int) -> tuple[bool, str, int]:
        """Atomically check quota and increment generation count.

        Prevents parallel requests from all passing a stale read.
        Returns (ok, reason, new_count).
        """
        period = self._period()
        path = self._path(tenant_id, period)
        with exclusive_lock(path):
            b = self._load_unlocked(path, tenant_id, period)
            if limit > 0 and b.generations >= limit:
                return False, f"generation_quota_exceeded:{limit}", b.generations
            b.generations += 1
            b.extra["generate"] = int(b.extra.get("generate", 0)) + 1
            self._save_unlocked(path, b)
            return True, "ok", b.generations

    def try_reserve_host_start(self, tenant_id: str, limit: int) -> tuple[bool, str, int]:
        """Atomically reserve a hosted-bot start against monthly host_starts (soft).

        Hosted-bot concurrent limit is enforced separately; this tracks starts.
        """
        period = self._period()
        path = self._path(tenant_id, period)
        with exclusive_lock(path):
            b = self._load_unlocked(path, tenant_id, period)
            # host_starts is informational; concurrent limit uses live count
            b.host_starts += 1
            b.extra["host_start"] = int(b.extra.get("host_start", 0)) + 1
            self._save_unlocked(path, b)
            return True, "ok", b.host_starts

    def check_rpm(self, tenant_id: str, limit: int) -> bool:
        """Process-safe API RPM via shared SQLite limiter."""
        return get_rate_limiter().allow(f"api:{tenant_id}", limit=limit, window_sec=60.0)


_METER: MeteringService | None = None


def get_metering() -> MeteringService:
    global _METER
    if _METER is None:
        _METER = MeteringService()
    return _METER
