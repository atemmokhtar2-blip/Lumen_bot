"""Canonical durable filesystem roots — never default to global /tmp.

systemd tmpfiles.d and container ephemeral /tmp wipe state and break locks,
rate-limit DBs, job queues, and session stores. All components must resolve
paths through this module (or OUTPUT_DIR / STATE_DIR set by the operator).
"""
from __future__ import annotations

from lumen.identity import DOTDIR_NAME, VAR_LIB_PATH

import os
from pathlib import Path

_RESOLVED: Path | None = None


def durable_data_dir() -> Path:
    """STATE_DIR → DATA_DIR → OUTPUT_DIR → /var/lib/lumen → ~/.lumen."""
    global _RESOLVED
    if _RESOLVED is not None:
        return _RESOLVED
    for key in ("STATE_DIR", "DATA_DIR", "OUTPUT_DIR"):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        p = Path(raw).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
            _RESOLVED = p.resolve()
            return _RESOLVED
        except OSError:
            continue
    for candidate in (
        Path(VAR_LIB_PATH),
        Path.home() / DOTDIR_NAME,
        Path(__file__).resolve().parents[1] / ".runtime",
    ):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            _RESOLVED = candidate.resolve()
            return _RESOLVED
        except OSError:
            continue
    p = Path.home() / DOTDIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    _RESOLVED = p.resolve()
    return _RESOLVED


def default_output_dir() -> str:
    """String form for env-style defaults (replaces /tmp/generated)."""
    return str(durable_data_dir())
