"""Per-user template instance store (Phase 1).

Redis preferred (lumen:templates:user:{uid}); in-process fallback for tests
and single-worker dev. Never stores bot tokens — only ids and schedule fields.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any

from lumen.templates.models import (
    TemplateInstance,
    TemplateInstanceStatus,
    TemplateLaunchMode,
)
from lumen.templates.policy import can_launch

logger = logging.getLogger(__name__)

_PREFIX = "lumen:templates:user:"
_TTL_SEC = int(os.getenv("TEMPLATES_STORE_TTL_SEC") or str(45 * 86400))  # 45d > permanent 30d
_lock = threading.RLock()
_mem: dict[int, list[dict[str, Any]]] = {}


def _redis():
    try:
        from lumen.platform.runtime_config import redis_url as _ru
        from lumen.platform.redis_client import connect_redis_url

        url = (_ru() or "").strip()
        if not url:
            return None
        r = connect_redis_url(
            url,
            decode_responses=True,
            socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT") or "2"),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT") or "3"),
        )
        r.ping()
        return r
    except Exception:
        return None


def _key(user_id: int) -> str:
    return f"{_PREFIX}{int(user_id)}"


def list_instances(user_id: int) -> list[TemplateInstance]:
    uid = int(user_id or 0)
    if uid <= 0:
        return []
    raw_list: list[dict[str, Any]] = []
    r = _redis()
    if r is not None:
        try:
            payload = r.get(_key(uid))
            if payload:
                data = json.loads(payload)
                if isinstance(data, list):
                    raw_list = [x for x in data if isinstance(x, dict)]
        except Exception as exc:
            logger.debug("templates store redis read failed: %s", type(exc).__name__)
    else:
        with _lock:
            raw_list = list(_mem.get(uid) or [])

    out: list[TemplateInstance] = []
    for item in raw_list:
        inst = TemplateInstance.from_dict(item)
        if inst is not None:
            out.append(inst)
    return out


def _save(user_id: int, instances: list[TemplateInstance]) -> None:
    uid = int(user_id)
    payload = [i.to_dict() for i in instances]
    r = _redis()
    if r is not None:
        try:
            r.setex(_key(uid), max(3600, _TTL_SEC), json.dumps(payload, ensure_ascii=False))
            return
        except Exception as exc:
            logger.debug("templates store redis write failed: %s", type(exc).__name__)
    with _lock:
        _mem[uid] = payload


def mark_expired(user_id: int, *, now: float | None = None) -> list[TemplateInstance]:
    """Flip RUNNING/PREPARING past expires_at → EXPIRED; persist; return list."""
    ts = float(now if now is not None else time.time())
    changed = False
    insts = list_instances(user_id)
    for inst in insts:
        if inst.status in {TemplateInstanceStatus.RUNNING, TemplateInstanceStatus.PREPARING}:
            if inst.expires_at > 0 and inst.expires_at <= ts:
                inst.status = TemplateInstanceStatus.EXPIRED
                changed = True
    if changed:
        _save(user_id, insts)
    return insts


def reserve_instance(
    user_id: int,
    *,
    template_id: str,
    mode: TemplateLaunchMode | str,
    trial_minutes: int | None = None,
    now: float | None = None,
) -> tuple[TemplateInstance | None, str]:
    """Policy check + create PREPARING slot. Returns (instance|None, reason)."""
    uid = int(user_id or 0)
    tid = (template_id or "").strip()
    if uid <= 0 or not tid:
        return None, "invalid_user_or_template"

    ts = float(now if now is not None else time.time())
    # Refresh expiry flags first so quota is honest
    current = mark_expired(uid, now=ts)
    decision = can_launch(mode=mode, instances=current, trial_minutes=trial_minutes, now=ts)
    if not decision.allowed:
        return None, decision.reason

    if isinstance(mode, str):
        mode = TemplateLaunchMode(mode.strip().lower())

    inst = TemplateInstance(
        instance_id=f"tpl_{uuid.uuid4().hex[:16]}",
        user_id=uid,
        template_id=tid,
        mode=mode,
        status=TemplateInstanceStatus.PREPARING,
        started_at=ts,
        expires_at=float(decision.expires_at),
        trial_minutes=int(decision.trial_minutes or 0),
    )
    current.append(inst)
    _save(uid, current)
    return inst, "ok"


def update_instance(user_id: int, instance_id: str, **fields: Any) -> TemplateInstance | None:
    uid = int(user_id or 0)
    iid = (instance_id or "").strip()
    if uid <= 0 or not iid:
        return None
    insts = list_instances(uid)
    found: TemplateInstance | None = None
    for inst in insts:
        if inst.instance_id != iid:
            continue
        for k, v in fields.items():
            if k == "status" and not isinstance(v, TemplateInstanceStatus):
                try:
                    v = TemplateInstanceStatus(str(v))
                except ValueError:
                    continue
            if k == "mode" and not isinstance(v, TemplateLaunchMode):
                try:
                    v = TemplateLaunchMode(str(v))
                except ValueError:
                    continue
            if hasattr(inst, k):
                setattr(inst, k, v)
        found = inst
        break
    if found is None:
        return None
    _save(uid, insts)
    return found


def clear_user_for_tests(user_id: int) -> None:
    """Test-only wipe."""
    uid = int(user_id or 0)
    r = _redis()
    if r is not None:
        try:
            r.delete(_key(uid))
        except Exception:
            pass
    with _lock:
        _mem.pop(uid, None)


__all__ = [
    "list_instances",
    "mark_expired",
    "reserve_instance",
    "update_instance",
    "clear_user_for_tests",
]
