"""Cooperative generation cancel — user can abort in-flight agent loops.

Mechanism:
  - request_cancel(user_id) sets an in-memory flag + optional marker file
  - agent_loop checks is_cancelled(user_id) each step and stops cleanly
  - clear_cancel(user_id) at start of a new generation

Not a hard kill of native code; cooperative only (same class as timeouts).
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Set

_LOCK = threading.Lock()
_CANCELLED: Set[int] = set()
_CANCEL_AT: dict[int, float] = {}


def _marker_path(user_id: int) -> Path | None:
    try:
        from lumen.platform.paths import default_output_dir
        base = Path(os.getenv("OUTPUT_DIR") or default_output_dir())
    except Exception:
        base = Path(os.getenv("OUTPUT_DIR") or "/tmp/lumen_output")
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base / f".cancel_{int(user_id)}"
    except Exception:
        return None


def request_cancel(user_id: int) -> None:
    uid = int(user_id or 0)
    if uid <= 0:
        return
    with _LOCK:
        _CANCELLED.add(uid)
        _CANCEL_AT[uid] = time.time()
    path = _marker_path(uid)
    if path is not None:
        try:
            path.write_text(str(time.time()), encoding="utf-8")
        except Exception:
            pass


def clear_cancel(user_id: int) -> None:
    uid = int(user_id or 0)
    with _LOCK:
        _CANCELLED.discard(uid)
        _CANCEL_AT.pop(uid, None)
    path = _marker_path(uid)
    if path is not None and path.exists():
        try:
            path.unlink()
        except Exception:
            pass


def is_cancelled(user_id: int) -> bool:
    uid = int(user_id or 0)
    if uid <= 0:
        return False
    with _LOCK:
        if uid in _CANCELLED:
            return True
    path = _marker_path(uid)
    if path is not None and path.is_file():
        return True
    return False
