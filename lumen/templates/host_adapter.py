"""Phase 4 — Template → permanent HostingService adapter (bounded).

Owns:
  - free-tier 3-slot policy (via TemplateService)
  - materialize into user sandbox
  - durable pending_host payload for token_handler
  - pre-flight checks before HostingService.start
  - post-start / failure status updates

Does not import Telegram UI. token_handler / templates_actions call into this.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from lumen.templates.models import (
    TemplateInstance,
    TemplateInstanceStatus,
    TemplateLaunchMode,
)
from lumen.templates.policy import FREE_MAX_RUNNING, evaluate_launch
from lumen.templates.service import get_template_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TemplateHostPlan:
    ok: bool
    reason: str = ""
    instance: TemplateInstance | None = None
    project_path: str = ""
    entry_point: str = ""
    pending_host: dict[str, Any] = field(default_factory=dict)


def _entry_for(root: Any) -> str:
    from pathlib import Path as _P
    r = _P(root)
    for name in ("main.py", "bot.py", "app.py"):
        if (r / name).is_file():
            return name
    return "main.py"


def prepare_permanent_launch(
    user_id: int,
    *,
    template_id: str,
    now: float | None = None,
) -> TemplateHostPlan:
    """Reserve + materialize + build pending_host. Fail-closed on any step."""
    uid = int(user_id or 0)
    tid = (template_id or "").strip()
    if uid <= 0 or not tid:
        return TemplateHostPlan(False, reason="invalid_user_or_template")

    ts = float(now if now is not None else time.time())
    svc = get_template_service()

    # Soft-expire before quota decision
    try:
        reconcile_expired(uid, now=ts, stop_hosts=False)
    except Exception:
        logger.debug("reconcile before permanent reserve soft-fail", exc_info=True)

    res = svc.reserve(
        uid,
        template_id=tid,
        mode=TemplateLaunchMode.PERMANENT,
        now=ts,
    )
    if not res.ok or res.instance is None:
        return TemplateHostPlan(False, reason=res.reason or "reserve_denied")

    inst = res.instance
    try:
        from lumen.templates.materialize import materialize_to_sandbox

        root = materialize_to_sandbox(uid, inst.template_id)
    except Exception as exc:
        logger.exception("template permanent materialize failed")
        try:
            svc.mark_stopped(uid, inst.instance_id)
        except Exception:
            pass
        return TemplateHostPlan(False, reason=f"materialize:{type(exc).__name__}")

    entry = _entry_for(root)
    try:
        from lumen.engine.services.runtime_planes import RuntimePlane
        plane = RuntimePlane.PERMANENT_HOST.value
    except Exception:
        plane = "permanent_host"

    try:
        from lumen.templates.product import resolve_max_template_slots
        _cap = int(resolve_max_template_slots(uid))
    except Exception:
        _cap = FREE_MAX_RUNNING

    pending = {
        "project_path": str(root),
        "user_id": uid,
        "entry_point": entry,
        "plane": plane,
        "source": "template",
        "template_id": inst.template_id,
        "template_instance_id": inst.instance_id,
        "expires_at": float(inst.expires_at or 0),
        "template_ttl_days": 30,
        "tenant_id": str(uid),  # production multi-tenant binding
        "max_template_slots": _cap,
    }
    try:
        meta = dict(inst.meta or {})
        meta.update(
            {
                "project_path": str(root),
                "plane": plane,
                "expires_at": float(inst.expires_at or 0),
            }
        )
        svc._patch(  # noqa: SLF001
            uid,
            inst.instance_id,
            status=TemplateInstanceStatus.PREPARING,
            meta=meta,
        )
    except Exception:
        logger.debug("template permanent meta patch failed", exc_info=True)

    return TemplateHostPlan(
        ok=True,
        reason="ok",
        instance=inst,
        project_path=str(root),
        entry_point=entry,
        pending_host=pending,
    )


def preflight_before_host_start(
    user_id: int,
    pending_host: dict[str, Any] | None,
    *,
    now: float | None = None,
) -> tuple[bool, str]:
    """Re-validate template free quota + instance still PREPARING / not expired."""
    ph = pending_host if isinstance(pending_host, dict) else {}
    if str(ph.get("source") or "") != "template":
        return True, "not_template"  # non-template hosts use other gates

    uid = int(user_id or 0)
    iid = str(ph.get("template_instance_id") or "").strip()
    if uid <= 0 or not iid:
        return False, "template_binding_missing"

    ts = float(now if now is not None else time.time())
    svc = get_template_service()
    try:
        reconcile_expired(uid, now=ts, stop_hosts=False)
    except Exception:
        pass

    insts = svc.list_user_instances(uid)
    target = next((i for i in insts if i.instance_id == iid), None)
    if target is None:
        return False, "template_instance_missing"
    if target.status == TemplateInstanceStatus.EXPIRED:
        return False, "template_instance_expired"
    if target.expires_at > 0 and target.expires_at <= ts:
        return False, "template_instance_expired"
    if target.status not in {
        TemplateInstanceStatus.PREPARING,
        TemplateInstanceStatus.RUNNING,
    }:
        return False, f"template_bad_status:{target.status.value}"

    # Count other actives excluding this instance — must stay under free cap
    others = [i for i in insts if i.instance_id != iid and i.is_active(ts)]
    try:
        from lumen.templates.product import resolve_max_template_slots
        cap = resolve_max_template_slots(uid)
    except Exception:
        cap = FREE_MAX_RUNNING
    if len(others) >= cap:
        return False, f"max_running_templates:{len(others)}>={cap}"
    return True, "ok"


def on_host_result(
    user_id: int,
    *,
    template_instance_id: str,
    ok: bool,
    host_instance_id: str = "",
) -> None:
    svc = get_template_service()
    iid = (template_instance_id or "").strip()
    if not iid:
        return
    if ok:
        svc.mark_running(int(user_id), iid, host_instance_id=(host_instance_id or "")[:80])
    else:
        svc._patch(  # noqa: SLF001
            int(user_id),
            iid,
            status=TemplateInstanceStatus.FAILED,
        )


def reconcile_expired(
    user_id: int,
    *,
    now: float | None = None,
    stop_hosts: bool = False,
) -> list[TemplateInstance]:
    """Mark clock-expired PREPARING/RUNNING → EXPIRED; optional host stop."""
    uid = int(user_id or 0)
    ts = float(now if now is not None else time.time())
    svc = get_template_service()
    insts = svc.list_user_instances(uid)
    changed = False
    for inst in insts:
        if inst.status not in {
            TemplateInstanceStatus.PREPARING,
            TemplateInstanceStatus.RUNNING,
        }:
            continue
        if inst.expires_at > 0 and inst.expires_at <= ts:
            inst.status = TemplateInstanceStatus.EXPIRED
            changed = True
            if stop_hosts and inst.host_instance_id:
                # Host stop is owned by the bot/hosting layer (no import here — boundary).
                logger.info(
                    "template expired uid=%s instance=%s host_id=%s (stop deferred to ops)",
                    uid,
                    inst.instance_id,
                    inst.host_instance_id[:40],
                )
    if changed:
        # persist via store
        try:
            svc._store.save_for_user(uid, insts)  # noqa: SLF001
        except Exception:
            for inst in insts:
                if inst.status == TemplateInstanceStatus.EXPIRED:
                    try:
                        svc._patch(uid, inst.instance_id, status=TemplateInstanceStatus.EXPIRED)  # noqa: SLF001
                    except Exception:
                        pass
    return insts


@dataclass(frozen=True, slots=True)
class TemplateStatusRow:
    instance_id: str
    template_id: str
    title: str
    mode: str
    status: str
    remaining_sec: int
    remaining_label_ar: str
    host_instance_id: str = ""


def list_user_status(user_id: int, *, now: float | None = None) -> list[TemplateStatusRow]:
    """Human-facing status rows after reconcile (no internal paths)."""
    uid = int(user_id or 0)
    ts = float(now if now is not None else time.time())
    if uid <= 0:
        return []
    reconcile_expired(uid, now=ts, stop_hosts=False)
    svc = get_template_service()
    rows: list[TemplateStatusRow] = []
    try:
        from lumen.templates.catalog import get_template
    except Exception:
        get_template = lambda _x: None  # type: ignore

    for inst in svc.list_user_instances(uid):
        rem = 0
        if inst.expires_at > 0:
            rem = max(0, int(inst.expires_at - ts))
        if rem >= 86400:
            label = f"{rem // 86400} يوم"
        elif rem >= 3600:
            label = f"{rem // 3600} ساعة"
        elif rem >= 60:
            label = f"{rem // 60} دقيقة"
        elif rem > 0:
            label = f"{rem} ثانية"
        else:
            label = "منتهٍ" if inst.expires_at > 0 else "—"

        title = inst.template_id
        try:
            spec = get_template(inst.template_id)
            if spec is not None:
                title = spec.title
        except Exception:
            pass

        mode_raw = inst.mode.value if hasattr(inst.mode, "value") else str(inst.mode)
        st_raw = inst.status.value if hasattr(inst.status, "value") else str(inst.status)
        try:
            from lumen.templates.product import status_label_ar, mode_label_ar
            st_show = status_label_ar(st_raw)
            mode_show = mode_label_ar(mode_raw)
        except Exception:
            st_show, mode_show = st_raw, mode_raw
        rows.append(
            TemplateStatusRow(
                instance_id=inst.instance_id,
                template_id=inst.template_id,
                title=title,
                mode=mode_show,
                status=st_show,
                remaining_sec=rem,
                remaining_label_ar=label,
                host_instance_id=inst.host_instance_id or "",
            )
        )
    # Active first
    order = {
        "running": 0, "شغّال": 0,
        "preparing": 1, "قيد التجهيز": 1,
        "failed": 2, "فشل": 2,
        "stopped": 3, "متوقف": 3,
        "expired": 4, "منتهٍ": 4,
    }
    rows.sort(key=lambda r: (order.get(r.status, 9), -r.remaining_sec))
    return rows


def stop_user_instance(user_id: int, instance_id: str) -> tuple[bool, str, str]:
    """Mark STOPPED and return (ok, reason, host_instance_id for optional host stop)."""
    uid = int(user_id or 0)
    iid = (instance_id or "").strip()
    if uid <= 0 or not iid:
        return False, "invalid", ""
    svc = get_template_service()
    insts = svc.list_user_instances(uid)
    target = next((i for i in insts if i.instance_id == iid), None)
    if target is None:
        return False, "not_found", ""
    host_id = target.host_instance_id or ""
    updated = svc.mark_stopped(uid, iid)
    if updated is None:
        return False, "update_failed", host_id
    return True, "ok", host_id


__all__ = [

    "TemplateHostPlan",
    "prepare_permanent_launch",
    "preflight_before_host_start",
    "on_host_result",
    "reconcile_expired",
]
