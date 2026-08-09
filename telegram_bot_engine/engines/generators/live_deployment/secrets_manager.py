"""
Secrets Manager — Specification 065.

Stores secrets in memory only, encrypted at rest in the process.
Never writes BOT_TOKEN to project source files that get committed,
and never returns or logs the raw token from public APIs.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets as _secrets
from typing import Dict, Optional

_log = logging.getLogger("engine.live_deployment.secrets")


def _xor_crypt(data: bytes, key: bytes) -> bytes:
    if not key:
        key = b"\x00"
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


class SecretsManager:
    """In-process encrypted secret store (no disk, no DB, no logs of values)."""

    def __init__(self, master_key: Optional[str] = None) -> None:
        env_key = os.getenv("TBE_SECRETS_KEY", "").strip()
        raw = (master_key or env_key or _secrets.token_hex(32)).encode("utf-8")
        self._key = hashlib.sha256(raw).digest()
        self._store: Dict[str, str] = {}  # id -> encrypted b64

    def put(self, secret_id: str, value: str) -> None:
        if not secret_id or value is None:
            return
        enc = _xor_crypt(value.encode("utf-8"), self._key)
        self._store[secret_id] = base64.urlsafe_b64encode(enc).decode("ascii")
        _log.info("Secret stored", extra={"secret_id": secret_id})  # never log value

    def get(self, secret_id: str) -> Optional[str]:
        blob = self._store.get(secret_id)
        if not blob:
            return None
        try:
            raw = base64.urlsafe_b64decode(blob.encode("ascii"))
            return _xor_crypt(raw, self._key).decode("utf-8")
        except Exception:
            return None

    def delete(self, secret_id: str) -> None:
        self._store.pop(secret_id, None)
        _log.info("Secret deleted", extra={"secret_id": secret_id})

    def has(self, secret_id: str) -> bool:
        return secret_id in self._store

    def redact(self, text: str, secret_id: str) -> str:
        """Replace secret value with *** in arbitrary text."""
        val = self.get(secret_id)
        if not val or not text:
            return text
        return text.replace(val, "***REDACTED***")


# Process-wide default store for the generation bot session
_GLOBAL = SecretsManager()


def get_secrets_manager() -> SecretsManager:
    return _GLOBAL
