"""Stable short symbol IDs for code intelligence indexes."""
from __future__ import annotations

import hashlib


def symbol_id(path: str, kind: str, name: str, line: int) -> str:
    raw = f"{path}:{kind}:{name}:{line}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


_sid = symbol_id

__all__ = ["symbol_id", "_sid"]
