"""Usage metering — generations, API calls, host-minutes (process-safe)."""
from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from b2b_platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.capability_maestro'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


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
    messages: int = 0
    characters: int = 0
    extra: dict[str, int] = field(default_factory=dict)


class MeteringService:
    """File JSON metering — **dev only**. Production must use MongoMeteringService."""

    def __init__(self, root: str | Path | None = None) -> None:
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        if env not in {"dev", "development", "local", "test"}:
            raise RuntimeError(
                "File-backed MeteringService cannot be constructed outside ENVIRONMENT=dev|local|test. "
                "Use MONGODB_URI / MongoMeteringService."
            )
        base = Path(root or os.getenv("OUTPUT_DIR") or _cm_default_output_dir())
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
        messages: int = 0,
        characters: int = 0,
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
            b.messages += int(messages)
            b.characters += int(characters)
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




class MongoMeteringService:
    """Metering in MongoDB — safe for multi-instance production."""

    def __init__(self, uri: str | None = None, *, db_name: str | None = None) -> None:
        from pymongo import MongoClient, ASCENDING
        self.uri = (uri or os.getenv("MONGODB_URI") or "").strip()
        if not self.uri:
            raise ValueError("MONGODB_URI required for MongoMeteringService")
        self.db_name = (db_name or os.getenv("MONGODB_DB") or "ai_agent_7h").strip()
        timeout = int(os.getenv("MONGODB_TIMEOUT_MS") or "8000")
        self._client = MongoClient(
            self.uri,
            serverSelectionTimeoutMS=timeout,
            connectTimeoutMS=timeout,
            retryWrites=True,
        )
        self.col = self._client[self.db_name]["metering"]
        try:
            self.col.create_index(
                [("tenant_id", ASCENDING), ("period", ASCENDING)],
                unique=True,
            )
        except Exception:
            pass

    def _period(self) -> str:
        return time.strftime("%Y-%m", time.gmtime())

    def snapshot(self, tenant_id: str) -> dict[str, Any]:
        period = self._period()
        doc = self.col.find_one({"tenant_id": str(tenant_id), "period": period}) or {}
        b = UsageBucket(tenant_id=str(tenant_id), period=period)
        for k in UsageBucket.__dataclass_fields__:
            if k in doc and k not in {"tenant_id", "period"}:
                setattr(b, k, doc[k])
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
        messages: int = 0,
        characters: int = 0,
        event: str = "",
    ) -> UsageBucket:
        period = self._period()
        inc = {
            "generations": int(generations),
            "api_calls": int(api_calls),
            "host_starts": int(host_starts),
            "host_minutes": float(host_minutes),
            "bytes_out": int(bytes_out),
            "messages": int(messages),
            "characters": int(characters),
        }
        if event:
            inc[f"extra.{event}"] = 1
        self.col.update_one(
            {"tenant_id": str(tenant_id), "period": period},
            {
                "$setOnInsert": {"tenant_id": str(tenant_id), "period": period},
                "$inc": {k: v for k, v in inc.items() if v},
            },
            upsert=True,
        )
        snap = self.snapshot(tenant_id)
        return UsageBucket(**{k: snap[k] for k in UsageBucket.__dataclass_fields__ if k in snap})



    def try_reserve_generation(self, tenant_id: str, limit: int) -> tuple[bool, str, int]:
        """Atomic quota check + increment via find_one_and_update."""
        period = self._period()
        filt = {"tenant_id": str(tenant_id), "period": period}
        if limit > 0:
            filt_ok = {**filt, "generations": {"$lt": int(limit)}}
            doc = self.col.find_one_and_update(
                filt_ok,
                {
                    "$setOnInsert": {"tenant_id": str(tenant_id), "period": period},
                    "$inc": {"generations": 1, "extra.generate": 1},
                },
                upsert=True,
                return_document=__import__('pymongo').ReturnDocument.AFTER,
            )
            if doc is None:
                # either exceeded or race — re-read
                cur = self.col.find_one(filt) or {}
                return False, f"generation_quota_exceeded:{limit}", int(cur.get("generations") or 0)
            return True, "ok", int(doc.get("generations") or 0)
        doc = self.col.find_one_and_update(
            filt,
            {
                "$setOnInsert": {"tenant_id": str(tenant_id), "period": period},
                "$inc": {"generations": 1, "extra.generate": 1},
            },
            upsert=True,
            return_document=__import__('pymongo').ReturnDocument.AFTER,
        )
        return True, "ok", int((doc or {}).get("generations") or 0)

    def try_reserve_host_start(self, tenant_id: str, limit: int) -> tuple[bool, str, int]:
        period = self._period()
        doc = self.col.find_one_and_update(
            {"tenant_id": str(tenant_id), "period": period},
            {
                "$setOnInsert": {"tenant_id": str(tenant_id), "period": period},
                "$inc": {"host_starts": 1, "extra.host_start": 1},
            },
            upsert=True,
            return_document=__import__('pymongo').ReturnDocument.AFTER,
        )
        return True, "ok", int((doc or {}).get("host_starts") or 0)

    def check_rpm(self, tenant_id: str, limit: int) -> bool:
        return get_rate_limiter().allow(f"api:{tenant_id}", limit=limit, window_sec=60.0)


def _is_dev_env() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    return env in {"dev", "development", "local", "test"}



_METER = None

_METER = None


def get_metering():
    """PostgreSQL metering in production; file only in explicit dev without DATABASE_URL."""
    global _METER
    if _METER is not None:
        return _METER
    from .runtime_config import database_url, is_dev, require_production_data_plane
    require_production_data_plane()
    pg = database_url()
    if pg:
        from .pg_store import PostgresMeteringService
        _METER = PostgresMeteringService(pg)
        return _METER
    if is_dev():
        _METER = MeteringService()
        return _METER
    raise RuntimeError("DATABASE_URL is required for metering.")
