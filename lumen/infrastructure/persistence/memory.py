"""In-memory repos for unit tests and local dry-runs."""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any

from lumen.domain.entities.job import Job
from lumen.domain.entities.tenant import Tenant
from lumen.domain.value_objects.job_status import JobStatus


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
            brand_name=str(fields.get("brand_name") or name),
            brand_logo_url=str(fields.get("brand_logo_url") or ""),
            primary_color=str(fields.get("primary_color") or "#2563eb"),
            support_email=str(fields.get("support_email") or ""),
            custom_domain=str(fields.get("custom_domain") or ""),
            api_key_hash=h,
            api_key_prefix=raw[:12],
            created_at=time.time(),
            active=True,
        )
        self._by_id[tid] = t
        self._by_hash[h] = tid
        return t, raw

    def update_white_label(self, tenant_id: str, **fields: Any) -> Tenant | None:
        t = self._by_id.get(tenant_id)
        if not t:
            return None
        for k in (
            "brand_name",
            "brand_logo_url",
            "primary_color",
            "support_email",
            "custom_domain",
            "name",
        ):
            if k in fields and fields[k] is not None:
                setattr(t, k, str(fields[k])[:300])
        return t

    def rotate_key(self, tenant_id: str) -> str | None:
        t = self._by_id.get(tenant_id)
        if not t:
            return None
        # drop old hash
        old = [h for h, tid in self._by_hash.items() if tid == tenant_id]
        for h in old:
            self._by_hash.pop(h, None)
        raw = f"sk_test_{secrets.token_urlsafe(24)}"
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        t.api_key_hash = h
        t.api_key_prefix = raw[:12]
        self._by_hash[h] = tenant_id
        return raw

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

    def cancel(self, job_id: str, *, tenant_id: str) -> Job | None:
        j = self._by_id.get(job_id)
        if not j or j.tenant_id != tenant_id:
            return None
        if j.status in JobStatus.TERMINAL:
            return j
        j.status = JobStatus.CANCELLED
        j.finished_at = time.time()
        return j

    def pause(self, job_id: str, *, tenant_id: str) -> Job | None:
        j = self._by_id.get(job_id)
        if not j or j.tenant_id != tenant_id:
            return None
        if j.status in JobStatus.TERMINAL:
            return None
        j.status = JobStatus.PAUSED
        return j

    def resume(self, job_id: str, *, tenant_id: str) -> Job | None:
        j = self._by_id.get(job_id)
        if not j or j.tenant_id != tenant_id:
            return None
        if j.status != JobStatus.PAUSED:
            return None
        j.status = JobStatus.RUNNING
        return j
