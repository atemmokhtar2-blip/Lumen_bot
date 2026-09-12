"""Store facade — prefer TemplateService; thin helpers for tests."""
from __future__ import annotations

from lumen.templates.models import TemplateInstance
from lumen.templates.service import TemplateService
from lumen.templates.store_memory import MemoryTemplateStore

# Module-level memory store for unit tests (no Redis)
_mem = MemoryTemplateStore()
_svc = TemplateService(store=_mem)


def list_instances(user_id: int) -> list[TemplateInstance]:
    return _svc.list_user_instances(user_id)


def reserve_instance(
    user_id: int,
    *,
    template_id: str,
    mode: object,
    trial_minutes: int | None = None,
    now: float | None = None,
) -> tuple[TemplateInstance | None, str]:
    res = _svc.reserve(
        user_id,
        template_id=template_id,
        mode=mode,  # type: ignore[arg-type]
        trial_minutes=trial_minutes,
        now=now,
    )
    return res.instance, res.reason


def update_instance(user_id: int, instance_id: str, **fields: object) -> TemplateInstance | None:
    if "status" in fields and fields.get("host_instance_id") is not None:
        return _svc.mark_running(
            user_id, instance_id, host_instance_id=str(fields.get("host_instance_id") or "")
        )
    if fields.get("status") is not None:
        from lumen.templates.models import TemplateInstanceStatus

        st = fields["status"]
        if st == TemplateInstanceStatus.RUNNING or str(st) == "running":
            return _svc.mark_running(
                user_id, instance_id, host_instance_id=str(fields.get("host_instance_id") or "")
            )
        if st == TemplateInstanceStatus.STOPPED or str(st) == "stopped":
            return _svc.mark_stopped(user_id, instance_id)
    return _svc._patch(user_id, instance_id, **fields)  # noqa: SLF001


def mark_expired(user_id: int, *, now: float | None = None) -> list[TemplateInstance]:
    import time
    from lumen.templates.models import TemplateInstanceStatus

    ts = float(now if now is not None else time.time())
    insts = list_instances(user_id)
    changed = False
    for inst in insts:
        if inst.status in {TemplateInstanceStatus.PREPARING, TemplateInstanceStatus.RUNNING}:
            if inst.expires_at > 0 and inst.expires_at <= ts:
                inst.status = TemplateInstanceStatus.EXPIRED
                changed = True
    if changed:
        _mem.save_for_user(int(user_id), insts)
    return insts


def clear_user_for_tests(user_id: int) -> None:
    _mem.clear(int(user_id))


__all__ = [
    "list_instances",
    "reserve_instance",
    "update_instance",
    "mark_expired",
    "clear_user_for_tests",
]
