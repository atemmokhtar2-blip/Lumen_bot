"""API key material generation (shape only — hashing elsewhere)."""
from __future__ import annotations

import secrets


def new_api_key(prefix: str = "sk_live") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


_new_api_key = new_api_key

__all__ = ["new_api_key", "_new_api_key"]
