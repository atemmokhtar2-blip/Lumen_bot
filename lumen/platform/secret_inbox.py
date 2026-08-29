"""Ephemeral encrypted inbox for secrets submitted via Mini App.

Flow:
  Mini App → POST /v1/telegram/secrets (initData validated)
  → encrypt secret with Fernet(TBE_TOKEN_SECRET)
  → store under user_id + kind with short TTL
  → Telegram bot polls/consumes on next user message or via pending flags

Never stores plaintext on disk. TTL default 10 minutes.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumen.secret_inbox")

_TTL_SEC = int(os.getenv("SECRET_INBOX_TTL_SEC") or "600")


def _cm_default_output_dir() -> str:
    try:
        from lumen.platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        p = Path.home() / ".lumen"
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


def _store_path() -> Path:
    root = Path(os.getenv("OUTPUT_DIR") or _cm_default_output_dir())
    d = root / "secret_inbox"
    d.mkdir(parents=True, exist_ok=True)
    return d / "inbox.json"


def _fernet():
    raw = (os.getenv("TBE_TOKEN_SECRET") or os.getenv("SECRET_INBOX_KEY") or "").strip()
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    is_dev = env in {"dev", "development", "local", "test"}
    if raw and len(raw) >= 16:
        digest = hashlib.sha256(raw.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    elif is_dev:
        # Dev-only derivation — never used when ENVIRONMENT=production
        tok = (os.getenv("TELEGRAM_BOT_TOKEN") or "dev").encode()
        digest = hashlib.sha256(b"lumen-secret-inbox-v1" + tok).digest()
        key = base64.urlsafe_b64encode(digest)
    else:
        raise RuntimeError(
            "TBE_TOKEN_SECRET (min 16 chars) required for secret_inbox in production"
        )
    try:
        from cryptography.fernet import Fernet
        return Fernet(key)
    except Exception as exc:
        raise RuntimeError(f"fernet_unavailable:{type(exc).__name__}") from exc


def _aes_key() -> bytes:
    """32-byte AES-256 key derived from TBE_TOKEN_SECRET (or dev fallback)."""
    raw = (os.getenv("TBE_TOKEN_SECRET") or os.getenv("SECRET_INBOX_KEY") or "").strip()
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "production").strip().lower()
    is_dev = env in {"dev", "development", "local", "test"}
    if raw and len(raw) >= 16:
        return hashlib.sha256(b"lumen-aesgcm-v1|" + raw.encode("utf-8")).digest()
    if is_dev:
        tok = (os.getenv("TELEGRAM_BOT_TOKEN") or "dev").encode()
        return hashlib.sha256(b"lumen-aesgcm-v1|" + tok).digest()
    raise RuntimeError("TBE_TOKEN_SECRET required for secret_inbox AES-GCM in production")


def _encrypt_aesgcm(plaintext: str, *, aad: bytes) -> str:
    """AES-256-GCM with AAD binding. Wire: gcm1.<b64url(nonce||ct||tag)>"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import secrets
    nonce = secrets.token_bytes(12)
    ct = AESGCM(_aes_key()).encrypt(nonce, plaintext.encode("utf-8"), aad)
    blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii").rstrip("=")
    return f"gcm1.{blob}"


def _decrypt_aesgcm(token: str, *, aad: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not token.startswith("gcm1."):
        raise ValueError("not_gcm")
    raw = token[5:]
    pad = "=" * (-len(raw) % 4)
    data = base64.urlsafe_b64decode(raw + pad)
    if len(data) < 12 + 16:
        raise ValueError("gcm_short")
    nonce, ct = data[:12], data[12:]
    return AESGCM(_aes_key()).decrypt(nonce, ct, aad).decode("utf-8")


@dataclass
class InboxItem:
    user_id: int
    kind: str  # bot | github
    ciphertext: str
    created_at: float
    expires_at: float
    purpose: str = ""  # host | run | clone | create
    meta: dict[str, Any] | None = None

    def to_row(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "kind": self.kind,
            "ciphertext": self.ciphertext,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "purpose": self.purpose,
            "meta": self.meta or {},
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "InboxItem":
        return cls(
            user_id=int(row.get("user_id") or 0),
            kind=str(row.get("kind") or ""),
            ciphertext=str(row.get("ciphertext") or ""),
            created_at=float(row.get("created_at") or 0),
            expires_at=float(row.get("expires_at") or 0),
            purpose=str(row.get("purpose") or ""),
            meta=dict(row.get("meta") or {}),
        )


def _locked(path: Path):
    """Exclusive file lock context for inbox read-modify-write."""
    import fcntl
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(".lock")
        with open(lock_path, "a+", encoding="utf-8") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    return _cm()


def _load_unlocked() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = list(data.get("items") or [])
        now = time.time()
        return [r for r in rows if float(r.get("expires_at") or 0) > now]
    except Exception:
        logger.exception("secret_inbox load failed")
        return []


def _save_unlocked(rows: list[dict[str, Any]]) -> None:
    path = _store_path()
    tmp = path.with_suffix(".tmp")
    payload = {"items": rows, "updated_at": time.time()}
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except Exception:
        pass


def _load() -> list[dict[str, Any]]:
    path = _store_path()
    with _locked(path):
        return _load_unlocked()


def _save(rows: list[dict[str, Any]]) -> None:
    path = _store_path()
    with _locked(path):
        _save_unlocked(rows)


def put_secret(
    *,
    user_id: int,
    kind: str,
    plaintext: str,
    purpose: str = "",
    meta: dict[str, Any] | None = None,
    ttl_sec: int | None = None,
) -> bool:
    uid = int(user_id or 0)
    if uid <= 0:
        return False
    k = (kind or "").strip().lower()
    if k not in {"bot", "github", "pat"}:
        return False
    if k == "pat":
        k = "github"
    secret = (plaintext or "").strip()
    if not secret or len(secret) > 512:
        return False
    try:
        aad = f"{uid}|{k}".encode("utf-8")
        ct = _encrypt_aesgcm(secret, aad=aad)
    except Exception:
        logger.exception("AES-GCM encrypt failed; trying Fernet fallback")
        try:
            f = _fernet()
            ct = f.encrypt(secret.encode("utf-8")).decode("ascii")
        except Exception:
            logger.exception("encrypt failed")
            return False
    now = time.time()
    ttl = int(ttl_sec if ttl_sec is not None else _TTL_SEC)
    item = InboxItem(
        user_id=uid,
        kind=k,
        ciphertext=ct,
        created_at=now,
        expires_at=now + max(60, ttl),
        purpose=(purpose or "")[:40],
        meta=dict(meta or {}),
    )
    path = _store_path()
    with _locked(path):
        rows = [
            r for r in _load_unlocked()
            if not (int(r.get("user_id") or 0) == uid and str(r.get("kind")) == k)
        ]
        rows.append(item.to_row())
        _save_unlocked(rows)
    return True


def consume_secret(*, user_id: int, kind: str) -> str | None:
    """Decrypt and remove one secret for user+kind. Returns plaintext or None.

    Atomic under exclusive flock — prevents double-consume races.
    """
    uid = int(user_id or 0)
    k = (kind or "").strip().lower()
    if k == "pat":
        k = "github"
    path = _store_path()
    found: dict[str, Any] | None = None
    with _locked(path):
        rows = _load_unlocked()
        kept: list[dict[str, Any]] = []
        for r in rows:
            if int(r.get("user_id") or 0) == uid and str(r.get("kind")) == k and found is None:
                found = r
            else:
                kept.append(r)
        if found is None:
            return None
        _save_unlocked(kept)
    try:
        blob = str(found["ciphertext"])
        aad = f"{uid}|{k}".encode("utf-8")
        if blob.startswith("gcm1."):
            return _decrypt_aesgcm(blob, aad=aad)
        # Legacy Fernet (pre-AES-GCM) — still supported for in-flight secrets
        f = _fernet()
        return f.decrypt(blob.encode("ascii"), ttl=_TTL_SEC + 60).decode("utf-8")
    except Exception:
        logger.exception("decrypt failed")
        return None


def peek_meta(*, user_id: int, kind: str) -> dict[str, Any] | None:
    uid = int(user_id or 0)
    k = (kind or "").strip().lower()
    if k == "pat":
        k = "github"
    for r in _load():
        if int(r.get("user_id") or 0) == uid and str(r.get("kind")) == k:
            return {
                "kind": k,
                "purpose": r.get("purpose") or "",
                "expires_at": r.get("expires_at"),
                "meta": r.get("meta") or {},
            }
    return None
