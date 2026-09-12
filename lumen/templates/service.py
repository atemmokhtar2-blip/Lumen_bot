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
from lumen.templates.errors import PolicyDenied
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
        decision = evaluate_launch(
            mode=mode,
            instances=current,
            now=ts,
            trial_minutes=trial_minutes,
            max_running=FREE_MAX_RUNNING,
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


def default_service() -> TemplateService:
    """Production preference: Redis store when reachable, else memory."""
    store: TemplateStorePort
    try:
        from lumen.templates.store_redis import RedisTemplateStore

        rs = RedisTemplateStore()
        rs.list_for_user(0)  # connectivity probe (empty)
        store = rs
    except Exception:
        store = MemoryTemplateStore()
    return TemplateService(store=store)


__all__ = ["ReserveResult", "TemplateService", "default_service", "PolicyDenied"]
