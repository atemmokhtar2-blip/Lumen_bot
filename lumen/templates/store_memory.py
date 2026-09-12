"""In-process TemplateStorePort — tests and single-worker dev only."""
from __future__ import annotations

import threading
from typing import Any

from lumen.templates.models import TemplateInstance, TemplateInstanceStatus


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
        return self._parse_rows(raw)

    @staticmethod
    def _parse_rows(raw: list[dict[str, Any]]) -> list[TemplateInstance]:
        out: list[TemplateInstance] = []
        for row in raw:
            try:
                out.append(TemplateInstance.from_dict(row))
            except Exception:
                continue
        return out

    def _expire_inplace(self, current: list[TemplateInstance], now: float) -> None:
        for inst in current:
            if inst.status in {TemplateInstanceStatus.PREPARING, TemplateInstanceStatus.RUNNING}:
                if inst.expires_at > 0 and inst.expires_at <= now:
                    inst.status = TemplateInstanceStatus.EXPIRED

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
            current = self._parse_rows(list(self._data.get(uid) or []))
            self._expire_inplace(current, now)
            active = sum(1 for i in current if i.is_active(now))
            if active >= max_active:
                self._data[uid] = [i.to_dict() for i in current]
                return False, f"max_running_templates:{active}>={max_active}"
            # Reject duplicate instance_id
            if any(i.instance_id == instance.instance_id for i in current):
                return False, "duplicate_instance_id"
            current.append(instance)
            self._data[uid] = [i.to_dict() for i in current]
            return True, "ok"

    def clear(self, user_id: int) -> None:
        with self._lock:
            self._data.pop(int(user_id), None)


__all__ = ["MemoryTemplateStore"]
