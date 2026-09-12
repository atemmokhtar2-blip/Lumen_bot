"""In-process TemplateStorePort — tests and single-worker dev only."""
from __future__ import annotations

import threading
from typing import Any

from lumen.templates.models import TemplateInstance


class MemoryTemplateStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[int, list[dict[str, Any]]] = {}

    def list_for_user(self, user_id: int) -> list[TemplateInstance]:
        uid = int(user_id or 0)
        if uid <= 0:
            return []
        with self._lock:
            raw = list(self._data.get(uid) or [])
        out: list[TemplateInstance] = []
        for row in raw:
            try:
                out.append(TemplateInstance.from_dict(row))
            except Exception:
                continue
        return out

    def save_for_user(self, user_id: int, instances: list[TemplateInstance]) -> None:
        uid = int(user_id)
        payload = [i.to_dict() for i in instances]
        with self._lock:
            self._data[uid] = payload

    def atomic_reserve(
        self,
        user_id: int,
        instance: TemplateInstance,
        *,
        max_active: int,
        now: float,
    ) -> tuple[bool, str]:
        uid = int(user_id)
        with self._lock:
            current = []
            for row in self._data.get(uid) or []:
                try:
                    current.append(TemplateInstance.from_dict(row))
                except Exception:
                    continue
            # Expire by clock inside the lock
            for inst in current:
                if inst.is_active(now) is False and inst.status.value in {"preparing", "running"}:
                    if inst.expires_at > 0 and inst.expires_at <= now:
                        from lumen.templates.models import TemplateInstanceStatus
                        inst.status = TemplateInstanceStatus.EXPIRED
            active = sum(1 for i in current if i.is_active(now))
            if active >= max_active:
                return False, f"max_running_templates:{active}>={max_active}"
            current.append(instance)
            self._data[uid] = [i.to_dict() for i in current]
            return True, "ok"

    def clear(self, user_id: int) -> None:
        with self._lock:
            self._data.pop(int(user_id), None)


__all__ = ["MemoryTemplateStore"]
