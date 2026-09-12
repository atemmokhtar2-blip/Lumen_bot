"""Redis TemplateStorePort — production path with optimistic lock on reserve."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from lumen.templates.errors import StoreError
from lumen.templates.models import TemplateInstance, TemplateInstanceStatus

logger = logging.getLogger(__name__)

_PREFIX = "lumen:templates:user:"
_TTL = int(os.getenv("TEMPLATES_STORE_TTL_SEC") or str(45 * 86400))


def _connect():
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


class RedisTemplateStore:
    def __init__(self, client: Any | None = None) -> None:
        self._r = client

    def _client(self):
        if self._r is not None:
            return self._r
        try:
            self._r = _connect()
        except Exception as exc:
            raise StoreError(f"redis_unavailable:{type(exc).__name__}") from exc
        if self._r is None:
            raise StoreError("redis_url_missing")
        return self._r

    @staticmethod
    def _key(user_id: int) -> str:
        return f"{_PREFIX}{int(user_id)}"

    def list_for_user(self, user_id: int) -> list[TemplateInstance]:
        r = self._client()
        try:
            payload = r.get(self._key(user_id))
        except Exception as exc:
            raise StoreError(f"redis_get_failed:{type(exc).__name__}") from exc
        if not payload:
            return []
        try:
            data = json.loads(payload)
        except Exception as exc:
            raise StoreError("redis_payload_corrupt") from exc
        if not isinstance(data, list):
            return []
        out: list[TemplateInstance] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            try:
                out.append(TemplateInstance.from_dict(row))
            except Exception:
                continue
        return out

    def save_for_user(self, user_id: int, instances: list[TemplateInstance]) -> None:
        r = self._client()
        payload = json.dumps([i.to_dict() for i in instances], ensure_ascii=False)
        try:
            r.setex(self._key(user_id), max(3600, _TTL), payload)
        except Exception as exc:
            raise StoreError(f"redis_set_failed:{type(exc).__name__}") from exc

    def atomic_reserve(
        self,
        user_id: int,
        instance: TemplateInstance,
        *,
        max_active: int,
        now: float,
    ) -> tuple[bool, str]:
        """WATCH + MULTI so two workers cannot both pass the free-tier cap."""
        r = self._client()
        key = self._key(user_id)
        for _attempt in range(5):
            try:
                r.watch(key)
                payload = r.get(key)
                current: list[TemplateInstance] = []
                if payload:
                    data = json.loads(payload)
                    if isinstance(data, list):
                        for row in data:
                            if isinstance(row, dict):
                                try:
                                    current.append(TemplateInstance.from_dict(row))
                                except Exception:
                                    continue
                for inst in current:
                    if (
                        inst.status in {TemplateInstanceStatus.PREPARING, TemplateInstanceStatus.RUNNING}
                        and inst.expires_at > 0
                        and inst.expires_at <= now
                    ):
                        inst.status = TemplateInstanceStatus.EXPIRED
                active = sum(1 for i in current if i.is_active(now))
                if active >= max_active:
                    r.unwatch()
                    return False, f"max_running_templates:{active}>={max_active}"
                current.append(instance)
                pipe = r.pipeline()
                pipe.setex(
                    key,
                    max(3600, _TTL),
                    json.dumps([i.to_dict() for i in current], ensure_ascii=False),
                )
                pipe.execute()
                return True, "ok"
            except Exception as exc:
                # WatchError or transient — retry
                name = type(exc).__name__
                if name in {"WatchError", "WatchError"} or "WatchError" in name:
                    continue
                logger.warning("templates redis atomic_reserve failed: %s", name)
                try:
                    r.unwatch()
                except Exception:
                    pass
                raise StoreError(f"redis_atomic_failed:{name}") from exc
        return False, "reserve_contention"


__all__ = ["RedisTemplateStore"]
