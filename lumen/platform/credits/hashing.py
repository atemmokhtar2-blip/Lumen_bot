"""Ledger entry hashing (shared by memory + postgres credit stores)."""
from __future__ import annotations

import hashlib
import json


def hash_entry(prev: str, payload: dict) -> str:
    raw = prev + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


_hash_entry = hash_entry

__all__ = ["hash_entry", "_hash_entry"]
