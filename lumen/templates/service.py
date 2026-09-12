"""Application service for templates Phase 0–1.

Orchestrates: catalog lookup → pure policy → store.atomic_reserve.
No Telegram, no HostingService imports.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Sequence

from lumen.templates.catalog import JsonTemplateCatalog
from lumen.templates.models import (
    TemplateInstance,
    TemplateInstanceStatus,
    TemplateLaunchMode,
    TemplateSpec,
    validate_template_id,
)
from lumen.templates.policy import FREE_MAX_RUNNING, LaunchPlan, evaluate_launch
from lumen.templates.ports import TemplateCatalogPort, TemplateStorePort
from lumen.templates.store_memory import MemoryTemplateStore


@dataclass(frozen=True, slots=True)
class ReserveResult:
    ok: bool
    reason: str
    instance: TemplateInstance | None = None
    plan: LaunchPlan | None = None


class TemplateService:
    def __init__(
        self,
        *,
        catalog: TemplateCatalogPort | None = None,
        store: TemplateStorePort | None = None,
    ) -> None:
        self._catalog: TemplateCatalogPort = catalog or JsonTemplateCatalog()
        self._store: TemplateStorePort = store or MemoryTemplateStore()

    def list_catalog(self) -> Sequence[TemplateSpec]:
        return self._catalog.list_enabled()

    def get_catalog_item(self, template_id: str) -> TemplateSpec | None:
        return self._catalog.get(template_id)

    def list_user_instances(self, user_id: int) -> list[TemplateInstance]:
        return self._store.list_for_user(int(user_id))

    def reserve(
        self,
        user_id: int,
        *,
        template_id: str,
        mode: TemplateLaunchMode | str,
        trial_minutes: int | None = None,
        now: float | None = None,
    ) -> ReserveResult:
        uid = int(user_id or 0)
        if uid <= 0:
            return ReserveResult(False, "invalid_user_id")
        try:
            tid = validate_template_id(template_id)
        except ValueError:
            return ReserveResult(False, "invalid_template_id")

        spec = self._catalog.get(tid)
        if spec is None:
            return ReserveResult(False, "template_not_found")

        ts = float(now if now is not None else time.time())
        current = self._store.list_for_user(uid)
        # Soft-expire in snapshot for policy (store also expires under lock)
        try:
            from lumen.templates.product import resolve_max_template_slots
            _cap = resolve_max_template_slots(uid)
        except Exception:
            _cap = FREE_MAX_RUNNING
        decision = evaluate_launch(
            mode=mode,
            instances=current,
            now=ts,
            trial_minutes=trial_minutes,
            max_running=_cap,
        )
        if decision.denied or decision.plan is None:
            return ReserveResult(False, decision.reason)

        plan = decision.plan
        inst = TemplateInstance(
            instance_id=f"tpl_{uuid.uuid4().hex[:16]}",
            user_id=uid,
            template_id=tid,
            mode=plan.mode,
            status=TemplateInstanceStatus.PREPARING,
            started_at=ts,
            expires_at=plan.expires_at,
            trial_minutes=plan.trial_minutes,
            meta={"template_version": int(spec.version)},
        )
        ok, reason = self._store.atomic_reserve(
            uid, inst, max_active=plan.max_running, now=ts
        )
        if not ok:
            return ReserveResult(False, reason)
        return ReserveResult(True, "ok", instance=inst, plan=plan)

    def mark_running(self, user_id: int, instance_id: str, *, host_instance_id: str = "") -> TemplateInstance | None:
        return self._patch(
            user_id,
            instance_id,
            status=TemplateInstanceStatus.RUNNING,
            host_instance_id=(host_instance_id or "").strip(),
        )

    def mark_stopped(self, user_id: int, instance_id: str) -> TemplateInstance | None:
        return self._patch(user_id, instance_id, status=TemplateInstanceStatus.STOPPED)

    def _patch(self, user_id: int, instance_id: str, **fields: object) -> TemplateInstance | None:
        uid = int(user_id or 0)
        iid = (instance_id or "").strip()
        if uid <= 0 or not iid:
            return None
        insts = self._store.list_for_user(uid)
        found = None
        for inst in insts:
            if inst.instance_id != iid:
                continue
            for k, v in fields.items():
                if hasattr(inst, k) and v is not None and v != "":
                    setattr(inst, k, v)
            found = inst
            break
        if found is None:
            return None
        self._store.save_for_user(uid, insts)
        return found


_svc_lock = __import__("threading").RLock()
_svc_singleton: TemplateService | None = None
_mem_store_singleton: MemoryTemplateStore | None = None


def _shared_memory_store() -> MemoryTemplateStore:
    global _mem_store_singleton
    if _mem_store_singleton is None:
        _mem_store_singleton = MemoryTemplateStore()
    return _mem_store_singleton


def default_service() -> TemplateService:
    """Build a service: Redis when reachable, else process-wide memory store."""
    try:
        from lumen.templates.store_redis import RedisTemplateStore
        from lumen.platform.runtime_config import redis_url

        if (redis_url() or "").strip():
            rs = RedisTemplateStore()
            rs._client()  # noqa: SLF001 — connectivity
            return TemplateService(store=rs)
    except Exception:
        pass
    return TemplateService(store=_shared_memory_store())


def get_template_service() -> TemplateService:
    """Process-wide TemplateService so quota is shared across requests/workers-in-process."""
    global _svc_singleton
    with _svc_lock:
        if _svc_singleton is None:
            _svc_singleton = default_service()
        return _svc_singleton


def reset_template_service_for_tests() -> None:
    """Test helper — drop singleton (keeps shared memory unless cleared)."""
    global _svc_singleton
    with _svc_lock:
        _svc_singleton = None


__all__ = [
    "ReserveResult",
    "TemplateService",
    "default_service",
    "get_template_service",
    "reset_template_service_for_tests",
]
