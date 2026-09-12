"""Small time helpers shared by memory services."""
from __future__ import annotations

import time


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


_now = utc_now_iso

__all__ = ["utc_now_iso", "_now"]
