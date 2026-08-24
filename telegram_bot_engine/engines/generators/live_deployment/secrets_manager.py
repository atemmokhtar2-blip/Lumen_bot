"""In-process secret store for deployment drivers.

Values are sealed with Fernet (enc2) via crypto_tokens — never logged.
"""
from __future__ import annotations

import secrets
from typing import Dict, Optional

from telegram_bot_engine.services.crypto_tokens import seal_token, unseal_token


class SecretsManager:
    """In-process sealed secret store (no disk, no DB, no logs of values)."""

    def __init__(self) -> None:
        self._store: Dict[str, str] = {}  # id -> sealed blob

    def put(self, value: str, secret_id: str | None = None) -> str:
        sid = secret_id or secrets.token_hex(8)
        self._store[sid] = seal_token(value)
        return sid

    def get(self, secret_id: str) -> Optional[str]:
        blob = self._store.get(secret_id)
        if not blob:
            return None
        try:
            return unseal_token(blob) or None
        except Exception:
            return None

    def delete(self, secret_id: str) -> None:
        self._store.pop(secret_id, None)

    def clear(self) -> None:
        self._store.clear()


_default_manager: SecretsManager | None = None


def get_secrets_manager() -> SecretsManager:
    """Process-wide SecretsManager singleton for deployment engine."""
    global _default_manager
    if _default_manager is None:
        _default_manager = SecretsManager()
    return _default_manager
