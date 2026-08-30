"""In-memory repos for unit tests and local dry-runs."""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any

from lumen.domain.entities.job import Job
from lumen.domain.entities.tenant import Tenant


class InMemoryTenantRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, Tenant] = {}
        self._by_hash: dict[str, str] = {}

    def get(self, tenant_id: str) -> Tenant | None:
        return self._by_id.get(tenant_id)

    def authenticate(self, api_key: str) -> Tenant | None:
        h = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        tid = self._by_hash.get(h)
        if not tid:
            return None
        t = self._by_id.get(tid)
        if not t or not t.active:
            return None
        return t

    def create(
        self,
        name: str,
        *,
        plan_id: str = "free",
        owner_telegram_id: int = 0,
        **fields: object,
    ) -> tuple[Tenant, str]:
        tid = secrets.token_hex(8)
        raw = f"sk_test_{secrets.token_urlsafe(24)}"
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        t = Tenant(
            tenant_id=tid,
            name=name,
            plan_id=plan_id,
            owner_telegram_id=int(owner_telegram_id or 0),
            api_key_hash=h,
            api_key_prefix=raw[:12],
            created_at=time.time(),
            active=True,
        )
        self._by_id[tid] = t
        self._by_hash[h] = tid
        return t, raw

    def list_all(self) -> list[Tenant]:
        return list(self._by_id.values())


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, Job] = {}

    def get(self, job_id: str) -> Job | None:
        return self._by_id.get(job_id)

    def create(self, job: Job) -> Job:
        self._by_id[job.job_id] = job
        return job

    def list_for_tenant(self, tenant_id: str, *, limit: int = 20) -> list[Job]:
        out = [j for j in self._by_id.values() if j.tenant_id == tenant_id]
        out.sort(key=lambda j: j.created_at, reverse=True)
        return out[: max(1, min(100, int(limit)))]
