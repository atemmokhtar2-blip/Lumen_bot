"""Market services — production-safe SQLite logic for generated bots.

This module is copied into generated projects as app/services/market.py.
No fake payment success; balances cannot go negative via debit helpers.
"""
from __future__ import annotations

import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from app.db import connect, init_db

# ── Simple per-process rate limit (sensitive ops) ─────────────────────────
_RATE: dict[str, float] = {}
_RATE_LOCK = threading.Lock()


