"""Durable Telegram user-session store — Redis primary (multi-worker safe).

Root model
----------
``context.user_data`` is process RAM only. Restarts and extra replicas wipe it.
Every request must:

  1. hydrate durable keys FROM Redis into ``user_data`` (Redis is source of truth)
  2. mutate ``user_data`` during the handler
  3. persist durable keys BACK to Redis

SQLite-on-disk was removed: Railway/ephemeral disks and multi-replica deployments
made it lose context. Redis is already mandatory for rate limits / jobs in this
project (``REDIS_URL`` / ``JOB_REDIS_URL``).

Dev/test without Redis may use an in-process memory backend only when
``SESSION_ALLOW_MEMORY=1`` and the runtime is not a deploy platform.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Protocol

logger = logging.getLogger("lumen.bot.session_store")

# Keys that survive restarts / cross-worker hops. Everything else stays RAM-only.
_DURABLE_KEYS = frozenset({
    # Generation / host pending flows
    "pending_run",
    "pending_live_run",
    "pending_deploy",
    "pending_host",
    "pending_clone_auth",
    "pending_create_repo",
    "pending_git_push",
    # Project / repo context
    "active_repo",
    "last_project_path",
    "active_bot_path",
    "last_clone_url",
    "repo_sections",
    # Conversation continuity
    "chat_history",
    "last_bot_request",
    "translated_preferred_keys",
    "translated_source",
    "force_generate_once",
    "engine_ui_await_generate",
    # Engine UI phase machine (was previously dropped — major lost-context bug)
    "engine_ui",
    # Preferences / onboarding
    "lang",
    "lumen_welcome_shown",
    "lumen_welcome_msg_id",
    # Multi-agent / HITL continuity
    "multi_agent_state_id",
    "multi_agent_pending",
})

_SECRET_KEYS = frozenset({
    "bot_token", "token", "telegram_bot_token", "api_token",
    "TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TOKEN", "github_token",
    "gh_token", "password", "secret", "api_key",
})

_KEY_PREFIX = "lumen:tg:session:"
_DEFAULT_TTL_SEC = 30 * 24 * 3600  # 30 days


class _RedisLike(Protocol):
    def get(self, name: str) -> Any: ...
    def set(self, name: str, value: Any, ex: int | None = None) -> Any: ...
    def delete(self, *names: str) -> Any: ...


def _redact_secrets(obj: Any) -> Any:
    """Never persist plaintext secrets. Drop bot tokens; seal other secrets if possible."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            kl = str(k).lower()
            is_secret = (
                k in _SECRET_KEYS
                or kl in _SECRET_KEYS
                or kl.endswith("_token")
                or kl.endswith("_secret")
                or kl.endswith("_password")
                or kl in {"token", "password", "api_key", "authorization"}
            )
            if is_secret:
                if kl in {
                    "bot_token", "token", "telegram_bot_token", "api_token",
                }:
                    continue
                if isinstance(v, str) and v.strip():
                    try:
                        from lumen.engine.services.crypto_tokens import seal_token
                        out[k] = seal_token(v)
                    except Exception:
                        pass
                continue
            out[k] = _redact_secrets(v)
        return out
    if isinstance(obj, list):
        return [_redact_secrets(x) for x in obj]
    return obj


def _filter_durable(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = _redact_secrets(dict(data or {}))
    keep: dict[str, Any] = {}
    for k in _DURABLE_KEYS:
        if k not in cleaned or cleaned[k] is None:
            continue
        keep[k] = cleaned[k]
    return keep


def _ttl_sec() -> int:
    raw = (os.getenv("SESSION_TTL_SEC") or "").strip()
    if not raw:
        return _DEFAULT_TTL_SEC
    try:
        return max(60, int(raw))
    except ValueError:
        return _DEFAULT_TTL_SEC


def _redis_key(user_id: int) -> str:
    return f"{_KEY_PREFIX}{int(user_id)}"


class _MemoryBackend:
    """Process-local dict — DEV/TEST only when Redis is intentionally skipped."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = threading.RLock()

    def get(self, name: str) -> str | None:
        with self._lock:
            return self._data.get(name)

    def set(self, name: str, value: Any, ex: int | None = None) -> bool:
        with self._lock:
            self._data[name] = value if isinstance(value, str) else str(value)
            return True

    def delete(self, *names: str) -> int:
        with self._lock:
            n = 0
            for name in names:
                if name in self._data:
                    del self._data[name]
                    n += 1
            return n


class SessionStore:
    """Redis-backed user session (JSON blob per Telegram user id)."""

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        client: _RedisLike | None = None,
        allow_memory: bool | None = None,
    ) -> None:
        self._client: _RedisLike
        self._backend_name: str
        self._lock = threading.RLock()

        if client is not None:
            self._client = client
            self._backend_name = "injected"
            return

        url = (redis_url or "").strip()
        if not url:
            try:
                from lumen.platform.runtime_config import redis_url as _cfg_redis
                url = (_cfg_redis() or "").strip()
            except Exception:
                url = (
                    (os.getenv("JOB_REDIS_URL") or os.getenv("REDIS_URL") or "")
                    .strip()
                )

        if url:
            import redis

            connect_to = float(os.getenv("REDIS_CONNECT_TIMEOUT") or "2")
            socket_to = float(os.getenv("REDIS_SOCKET_TIMEOUT") or "2")
            r = redis.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=connect_to,
                socket_timeout=socket_to,
            )
            r.ping()
            self._client = r
            self._backend_name = "redis"
            logger.info("session_store backend=redis ttl=%s", _ttl_sec())
            return

        # No Redis URL — only allowed in explicit local/dev with opt-in
        if allow_memory is None:
            allow_memory = (os.getenv("SESSION_ALLOW_MEMORY") or "").strip().lower() in {
                "1", "true", "yes", "on",
            }
        deploy_markers = (
            "RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME",
            "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV",
        )
        on_platform = any((os.getenv(m) or "").strip() for m in deploy_markers)
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        is_local = env in {"dev", "development", "local", "test"} and not on_platform

        if allow_memory and is_local:
            self._client = _MemoryBackend()
            self._backend_name = "memory"
            logger.warning(
                "session_store backend=memory (SESSION_ALLOW_MEMORY=1, local only) — "
                "not multi-worker safe"
            )
            return

        raise RuntimeError(
            "REDIS_URL is required for Telegram session persistence "
            "(multi-worker / restart-safe context). "
            "Set REDIS_URL, or for local only: ENVIRONMENT=dev SESSION_ALLOW_MEMORY=1"
        )

    @property
    def backend(self) -> str:
        return self._backend_name

    def load(self, user_id: int) -> dict[str, Any]:
        key = _redis_key(user_id)
        try:
            raw = self._client.get(key)
        except Exception as exc:
            logger.warning(
                "session_store load failed uid=%s: %s:%s",
                user_id, type(exc).__name__, str(exc)[:120],
            )
            return {}
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save(self, user_id: int, data: dict[str, Any]) -> None:
        """Merge durable keys into Redis (does not wipe keys absent from this payload)."""
        incoming = _filter_durable(dict(data or {}))
        with self._lock:
            existing = self.load(user_id)
            merged = dict(existing)
            for k, v in incoming.items():
                merged[k] = v
            payload = json.dumps(merged, ensure_ascii=False, default=str)
            key = _redis_key(user_id)
            try:
                self._client.set(key, payload, ex=_ttl_sec())
            except Exception as exc:
                logger.error(
                    "session_store save failed uid=%s: %s:%s",
                    user_id, type(exc).__name__, str(exc)[:120],
                )
                raise

    def clear(self, user_id: int) -> None:
        try:
            self._client.delete(_redis_key(user_id))
        except Exception as exc:
            logger.warning(
                "session_store clear failed uid=%s: %s:%s",
                user_id, type(exc).__name__, str(exc)[:120],
            )

    def hydrate(self, user_id: int, user_data: dict[str, Any] | None) -> dict[str, Any]:
        """Load durable session into ``user_data`` — Redis is source of truth.

        Overwrites durable keys in ``user_data`` with Redis values so multi-worker
        and restart paths always see the last persisted context (not stale RAM).
        """
        if user_data is None:
            return {}
        saved = self.load(int(user_id))
        if not saved:
            return user_data
        for k, v in saved.items():
            if k in _DURABLE_KEYS:
                user_data[k] = v
        return user_data


_store: SessionStore | None = None
_store_lock = threading.Lock()


def get_session_store() -> SessionStore:
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            _store = SessionStore()
        return _store


def reset_session_store_for_tests() -> None:
    """Clear singleton — tests only."""
    global _store
    with _store_lock:
        _store = None


__all__ = [
    "SessionStore",
    "get_session_store",
    "reset_session_store_for_tests",
    "_DURABLE_KEYS",
]
