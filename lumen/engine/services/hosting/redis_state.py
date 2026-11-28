"""Redis write-through registry for PERMANENT_HOST instance state.

Root fix for «state lost when container/VM dies on a node»:
  - Durable truth remains Postgres/SQLite via HostingStateStore
  - Redis holds a hot, multi-worker visible copy of running/stopped metadata
  - Workers hydrate from Redis+DB; ingress/health read Redis without disk

Requires REDIS_URL / JOB_REDIS_URL (same as session store). Dev may skip when
ENVIRONMENT=dev|test and SESSION_ALLOW_MEMORY=1 (registry becomes no-op).
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional
from lumen.platform.redis_client import connect_redis_url

logger = logging.getLogger("tbe.hosting.redis_state")

_PREFIX = "lumen:host:inst:"
_USER_PREFIX = "lumen:host:user:"
_TTL = int((os.environ.get("TBE_HOST_REDIS_TTL") or "86400").strip() or "86400")


def _client():
    url = (
        (os.environ.get("JOB_REDIS_URL") or "")
        or (os.environ.get("REDIS_URL") or "")
    ).strip()
    if not url:
        try:
            from lumen.platform.runtime_config import redis_url as _cfg

            url = (_cfg() or "").strip()
        except Exception:
            url = ""
    if not url:
        env = (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").lower()
        if env in {"dev", "development", "local", "test"}:
            return None
        raise RuntimeError(
            "REDIS_URL required for host instance registry (multi-worker state). "
            "Set REDIS_URL or JOB_REDIS_URL."
        )
    import redis

    return connect_redis_url(
        url,
        decode_responses=True,
        socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT") or "2"),
        socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT") or "2"),
    )


def _dump(inst: Any) -> dict[str, Any]:
    if hasattr(inst, "__dataclass_fields__"):
        from dataclasses import asdict

        d = asdict(inst)
    elif isinstance(inst, dict):
        d = dict(inst)
    else:
        d = dict(inst)
    d["updated_at"] = time.time()
    # never store secrets
    d.pop("bot_token", None)
    d.pop("token", None)
    return d


def put_instance(inst: Any) -> bool:
    """Write-through instance record. Returns False if Redis unavailable in dev."""
    try:
        r = _client()
        if r is None:
            return False
        d = _dump(inst)
        iid = str(d.get("instance_id") or "")
        uid = int(d.get("user_id") or 0)
        tid = str(d.get("tenant_id") or "")
        if not iid:
            return False
        from lumen.platform.tenant_isolation import host_instance_redis_key, host_user_index_key
        pipe = r.pipeline()
        payload = json.dumps(d, ensure_ascii=False)
        if tid:
            # Tenant-bound records must never enter the flat user namespace.
            pipe.setex(host_instance_redis_key(iid, tenant_id=tid), _TTL, payload)
            if uid:
                pipe.sadd(host_user_index_key(uid, tenant_id=tid), iid)
                pipe.expire(host_user_index_key(uid, tenant_id=tid), _TTL)
        else:
            # Only non-tenant (e.g. Telegram) instances use the flat namespace.
            pipe.setex(host_instance_redis_key(iid), _TTL, payload)
            if uid:
                pipe.sadd(host_user_index_key(uid), iid)
                pipe.expire(host_user_index_key(uid), _TTL)
        pipe.execute()
        return True
    except Exception as exc:
        logger.warning("redis_state put failed: %s", type(exc).__name__)
        return False


def get_instance(instance_id: str, *, tenant_id: str = "") -> Optional[dict[str, Any]]:
    try:
        r = _client()
        if r is None:
            return None
        from lumen.platform.tenant_isolation import host_instance_redis_key
        iid = str(instance_id)
        raw = r.get(host_instance_redis_key(iid, tenant_id=tenant_id or ""))
        if not raw:
            return None
        d = json.loads(raw)
        stored_tenant = str(d.get("tenant_id") or "").strip()
        requested_tenant = str(tenant_id or "").strip()
        # Exact namespace match; no cross-tenant or legacy-flat fallback.
        if stored_tenant != requested_tenant:
            return None
        return d
    except Exception:
        return None


def list_for_user(user_id: int, *, tenant_id: str = "") -> list[dict[str, Any]]:
    try:
        r = _client()
        if r is None:
            return []
        from lumen.platform.tenant_isolation import host_user_index_key
        ids = r.smembers(host_user_index_key(int(user_id), tenant_id=tenant_id or "")) or set()
        out: list[dict[str, Any]] = []
        for iid in ids:
            d = get_instance(str(iid), tenant_id=tenant_id or "")
            if d:
                out.append(d)
        return out
    except Exception:
        logger.warning("redis_state list_for_user failed", exc_info=True)
        return []


def delete_instance(
    instance_id: str,
    user_id: int | None = None,
    *,
    tenant_id: str = "",
) -> None:
    try:
        r = _client()
        if r is None:
            return
        from lumen.platform.tenant_isolation import host_instance_redis_key, host_user_index_key
        pipe = r.pipeline()
        pipe.delete(host_instance_redis_key(str(instance_id), tenant_id=tenant_id or ""))
        if user_id is not None:
            pipe.srem(
                host_user_index_key(int(user_id), tenant_id=tenant_id or ""),
                str(instance_id),
            )
        pipe.execute()
    except Exception:
        logger.warning("redis_state delete failed", exc_info=True)


__all__ = [
    "put_instance",
    "get_instance",
    "list_for_user",
    "delete_instance",
]
