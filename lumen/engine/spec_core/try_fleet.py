"""Bounded live-try fleet for massive multi-tenant bot trials.

Design goals (horizontal scale foundation):
  - Hard global concurrent try limit (machine / process local)
  - Per-user concurrent try limit
  - Short TTL runs (BUILDER_TRY_SECONDS)
  - No shared host token; each try uses the end-user bot token only
  - Fail-fast when capacity is full instead of queueing forever

For true planetary scale you still need many worker hosts behind a queue;
this module is the single-node control plane that keeps one box stable.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_global = 0
_active_by_user: dict[int, int] = {}
_slots: dict[str, "TrySlot"] = {}


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except Exception:
        return default


def max_global_tries() -> int:
    return _env_int("MAX_GLOBAL_LIVE_TRIES", 32)


def max_user_tries() -> int:
    return _env_int("MAX_USER_LIVE_TRIES", 1)


def try_seconds() -> float:
    try:
        return max(15.0, float(os.getenv("BUILDER_TRY_SECONDS", os.getenv("LIVE_RUN_SECONDS", "120"))))
    except Exception:
        return 120.0


@dataclass
class TrySlot:
    slot_id: str
    user_id: int
    project_path: str
    started_at: float = field(default_factory=time.time)
    thread: threading.Thread | None = None


def fleet_status() -> dict[str, Any]:
    with _lock:
        return {
            "active_global": _active_global,
            "max_global": max_global_tries(),
            "active_by_user": dict(_active_by_user),
            "max_per_user": max_user_tries(),
            "slots": len(_slots),
        }


def acquire_slot(user_id: int, project_path: str) -> tuple[bool, str, str | None]:
    """Reserve capacity. Returns (ok, message, slot_id)."""
    global _active_global
    uid = int(user_id or 0)
    with _lock:
        if _active_global >= max_global_tries():
            return False, "السعة ممتلئة حاليًا — حاول بعد لحظات (حد التشغيل العام).", None
        if _active_by_user.get(uid, 0) >= max_user_tries():
            return False, "لديك تجربة تشغيل قيد التنفيذ بالفعل.", None
        _active_global += 1
        _active_by_user[uid] = _active_by_user.get(uid, 0) + 1
        slot_id = f"{uid}-{int(time.time()*1000)}"
        _slots[slot_id] = TrySlot(slot_id=slot_id, user_id=uid, project_path=str(project_path))
        return True, "reserved", slot_id


def release_slot(slot_id: str | None, user_id: int) -> None:
    global _active_global
    if not slot_id:
        return
    uid = int(user_id or 0)
    with _lock:
        if slot_id in _slots:
            del _slots[slot_id]
        _active_global = max(0, _active_global - 1)
        cur = _active_by_user.get(uid, 0)
        if cur <= 1:
            _active_by_user.pop(uid, None)
        else:
            _active_by_user[uid] = cur - 1


def start_try(
    *,
    user_id: int,
    project_path: str | Path,
    bot_token: str,
    on_done: Callable[[Any], None] | None = None,
) -> tuple[bool, str]:
    """Start a bounded live try in a daemon thread if capacity allows."""
    ok, msg, slot_id = acquire_slot(user_id, str(project_path))
    if not ok or not slot_id:
        return False, msg

    path = Path(project_path)
    token = (bot_token or "").strip()
    seconds = try_seconds()

    def worker() -> None:
        report = None
        try:
            from lumen.engine.services.live_runner import run_bot_project

            report = run_bot_project(
                project_path=path,
                bot_token=token,
                entry_hint="main.py",
                run_seconds=seconds,
            )
        except Exception as exc:
            logger.exception("try fleet worker failed user=%s", user_id)

            class _Err:
                ok = False
                phase = "error"
                message = f"{type(exc).__name__}: {exc}"

                def to_user_text(self) -> str:
                    return f"❌ فشل التشغيل: {self.message}"[:500]

            report = _Err()
        finally:
            release_slot(slot_id, user_id)
            if on_done is not None and report is not None:
                try:
                    on_done(report)
                except Exception:
                    logger.exception("on_done failed")

    th = threading.Thread(target=worker, name=f"try-{slot_id}", daemon=True)
    with _lock:
        if slot_id in _slots:
            _slots[slot_id].thread = th
    th.start()
    return True, f"started:{slot_id}:ttl={int(seconds)}s"


__all__ = [
    "start_try",
    "fleet_status",
    "acquire_slot",
    "release_slot",
    "max_global_tries",
    "max_user_tries",
    "try_seconds",
]
