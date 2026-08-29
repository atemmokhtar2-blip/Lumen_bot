"""Shared API-key pool with cooldown + ordered failover.

Gemini: GEMINI_API_KEY / GOOGLE_* aliases + GEMINI_API_KEY_0..150 + GEMINI_API_KEYS bulk
Groq:   GROQ_API_KEY + GROQ_API_KEY_0..100 + GROQ_API_KEYS
Qwen:   QWEN_API_KEY / DASHSCOPE_API_KEY + QWEN_API_KEY_0..100 + QWEN_API_KEYS (sk-ws-)

When a key hits auth/rate limits it is cooled down with adaptive duration:
  rate/429  → short (default 8s) so the next key is tried almost immediately
  auth/401  → longer (default 300s) so bad keys are skipped
Callers must break to the next key on rate/auth errors (do not retry models on a hot key).
If every key is cooling, all keys are still returned ordered by soonest-ready so
the request can keep rotating without surfacing a hard failure to the user.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Iterable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key inventory: loaded ONCE at process start (or explicit invalidate).
# Cooldowns: ONE backend — Redis when REDIS_URL is set, else process-local (dev only).
# ---------------------------------------------------------------------------
_COOLDOWN_LOCAL: dict[str, float] = {}  # monotonic; single-process lab only
_REDIS_COOLDOWN_PREFIX = "tbe:llm:cd:"
_REDIS_CLIENT = None  # lazy singleton
_REDIS_INIT_TRIED = False

# Boot snapshot: (gemini, groq, qwen) lists of (source, key)
_BOOT_KEYS: dict[str, list[tuple[str, str]]] | None = None


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _redis():
    """Process-wide Redis client for key cooldowns (shared across workers)."""
    global _REDIS_CLIENT, _REDIS_INIT_TRIED
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    if _REDIS_INIT_TRIED and _REDIS_CLIENT is None:
        return None
    _REDIS_INIT_TRIED = True
    try:
        url = (os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip()
        if not url:
            return None
        import redis
        client = redis.Redis.from_url(
            url,
            socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT") or "2"),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT") or "2"),
            decode_responses=True,
        )
        client.ping()
        _REDIS_CLIENT = client
        return _REDIS_CLIENT
    except Exception:
        logger.warning("LLM key cooldown Redis unavailable — single-worker local only")
        _REDIS_CLIENT = None
        return None


def _normalize(raw: str) -> str:
    val = (raw or "").strip()
    # strip accidental quotes from secret UIs
    if len(val) >= 2 and val[0] == val[-1] and val[0] in {"'", '"'}:
        val = val[1:-1].strip()
    return val


def cooldown_seconds(env_name: str, default: float = 60.0) -> float:
    try:
        return max(0.0, float(os.getenv(env_name) or str(default)))
    except ValueError:
        return default


def mark_cooldown(
    source: str,
    *,
    seconds: float | None = None,
    env_name: str = "KEY_COOLDOWN_SEC",
    reason: str = "rate",
) -> None:
    """Cool a key. ``reason`` selects adaptive default duration when ``seconds`` is None.

    reason:
      rate|429|quota  → KEY_RATE_COOLDOWN_SEC (default 8) — rotate to next key ASAP
      auth|401|403|invalid → KEY_AUTH_COOLDOWN_SEC (default 300)
      other → env_name default 20
    """
    if seconds is None:
        r = (reason or "rate").strip().lower()
        if r in {"rate", "429", "quota", "resource_exhausted"}:
            sec = cooldown_seconds("KEY_RATE_COOLDOWN_SEC", 8.0)
            # allow per-provider override via env_name when set lower intentionally
            alt = cooldown_seconds(env_name, sec)
            sec = min(sec, alt) if alt > 0 else sec
        elif r in {"auth", "401", "403", "invalid", "forbidden"}:
            sec = cooldown_seconds("KEY_AUTH_COOLDOWN_SEC", 300.0)
        else:
            sec = cooldown_seconds(env_name, 20.0)
    else:
        sec = float(seconds)
    if sec <= 0:
        return
    r = _redis()
    if r is not None:
        # SINGLE backend: Redis only (no parallel local state that drifts across workers)
        try:
            key = f"{_REDIS_COOLDOWN_PREFIX}{source}"
            new_ms = max(1, int(sec * 1000))
            lua = """
local cur = redis.call('PTTL', KEYS[1])
local want = tonumber(ARGV[1])
if cur == false or cur < 0 or want > cur then
  redis.call('SET', KEYS[1], '1', 'PX', want)
  return 1
end
return 0
"""
            r.eval(lua, 1, key, new_ms)
            # mirror local only as read-cache for same worker (optional, same TTL clock)
            _COOLDOWN_LOCAL[source] = time.monotonic() + sec
        except Exception as exc:
            logger.exception("redis cooldown failed source=%s", source)
            raise RuntimeError(f"redis_cooldown_failed:{type(exc).__name__}") from exc
    else:
        env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
        if env in {"production", "prod", "staging"}:
            raise RuntimeError(
                "REDIS_URL required for LLM key cooldowns in production "
                "(multi-worker shared state)"
            )
        until = time.monotonic() + sec
        prev = _COOLDOWN_LOCAL.get(source, 0.0)
        if until > prev:
            _COOLDOWN_LOCAL[source] = until
    logger.warning("key cooldown source=%s reason=%s for %.0fs", source, reason, sec)


def is_cooling(source: str) -> bool:
    """Single backend: Redis if configured, else local monotonic."""
    r = _redis()
    if r is not None:
        try:
            return bool(r.exists(f"{_REDIS_COOLDOWN_PREFIX}{source}"))
        except Exception:
            logger.exception("redis is_cooling failed source=%s", source)
            return True  # fail closed: treat as cooling if Redis errors
    return _COOLDOWN_LOCAL.get(source, 0.0) > time.monotonic()


def clear_cooldown(source: str) -> None:
    _COOLDOWN_LOCAL.pop(source, None)
    r = _redis()
    if r is not None:
        try:
            r.delete(f"{_REDIS_COOLDOWN_PREFIX}{source}")
        except Exception:
            logger.exception("redis clear_cooldown failed source=%s", source)



def _ensure_boot_keys() -> None:
    """Load all provider keys once per process (boot-time / first use)."""
    global _BOOT_KEYS
    if _BOOT_KEYS is not None:
        return
    _BOOT_KEYS = {
        "gemini": list(_gemini_keys_uncached()),
        "groq": list(_groq_keys_uncached()),
        "qwen": list(_qwen_keys_uncached()),
    }
    logger.info(
        "LLM key pool loaded gemini=%s groq=%s qwen=%s",
        len(_BOOT_KEYS["gemini"]),
        len(_BOOT_KEYS["groq"]),
        len(_BOOT_KEYS["qwen"]),
    )


def invalidate_key_cache() -> None:
    """Force re-read of env/secret files after rotation."""
    global _BOOT_KEYS
    _BOOT_KEYS = None

def collect_env_keys(
    *,
    primary_names: Iterable[str],
    numbered_prefix: str,
    numbered_start: int,
    numbered_end: int,
) -> list[tuple[str, str]]:
    """Return ordered unique (source_name, key) pairs."""
    resolved: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(name: str, raw: str) -> None:
        val = _normalize(raw)
        if val and val not in seen:
            resolved.append((name, val))
            seen.add(val)

    for name in primary_names:
        _add(name, os.getenv(name) or "")

    for idx in range(numbered_start, numbered_end + 1):
        name = f"{numbered_prefix}{idx}"
        _add(name, os.getenv(name) or "")

    # case-insensitive scan for the same names (Railway/env typos)
    wanted = {n.upper() for n in primary_names}
    for idx in range(numbered_start, numbered_end + 1):
        wanted.add(f"{numbered_prefix}{idx}".upper())
    try:
        for k, v in list(os.environ.items()):
            ku = (k or "").strip().upper()
            if ku in wanted:
                _add(k, v or "")
    except Exception:
        logger.exception("env scan failed for prefix=%s", numbered_prefix)

    return resolved


def available_keys(
    all_keys: list[tuple[str, str]],
    *,
    failover_enabled: bool = True,
) -> list[tuple[str, str]]:
    """Keys ready for use, ordered for fastest rotation.

    - Prefer keys not in cooldown (original pool order preserved among ready).
    - If every key is cooling, return **all** keys ordered by soonest-ready so
      callers can still walk the pool instead of failing the user request.
    - When failover is disabled, still return the full list only if a single key
      exists; otherwise first key only (legacy).
    """
    if not all_keys:
        return []
    if not failover_enabled:
        return all_keys[:1]

    def _until(source: str) -> float:
        """Soonest-ready ranking: prefer Redis PTTL (shared), else local monotonic."""
        r = _redis()
        if r is not None:
            try:
                pttl = r.pttl(f"{_REDIS_COOLDOWN_PREFIX}{source}")
                if pttl is not None and int(pttl) > 0:
                    return time.time() + (int(pttl) / 1000.0)
            except Exception:
                pass
        return _COOLDOWN_LOCAL.get(source, 0.0)

    ready = [(s, k) for s, k in all_keys if not is_cooling(s)]
    if ready:
        return ready
    # all cooling — full pool by soonest-ready (fast sequential retry)
    return sorted(all_keys, key=lambda sk: _until(sk[0]))


def gemini_keys() -> list[tuple[str, str]]:
    _ensure_boot_keys()
    assert _BOOT_KEYS is not None
    return list(_BOOT_KEYS["gemini"])


def _gemini_keys_uncached() -> list[tuple[str, str]]:
    """GEMINI_API_KEY (+ aliases) + GEMINI_API_KEY_0..150 + bulk GEMINI_API_KEYS.

    Bulk formats (any one):
      GEMINI_API_KEYS=key_a,key_b,key_c
      GEMINI_API_KEYS multiline (one key per line)
    """
    primary = (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENERATIVE_AI_API_KEY",
        "GENAI_API_KEY",
        "GEMINI_KEY",
        "GOOGLE_AI_API_KEY",
    )
    keys = collect_env_keys(
        primary_names=primary,
        numbered_prefix="GEMINI_API_KEY_",
        numbered_start=0,
        numbered_end=150,
    )
    bulk = (os.getenv("GEMINI_API_KEYS") or os.getenv("GOOGLE_API_KEYS") or "").strip()
    if bulk:
        seen = {k for _, k in keys}
        for i, line in enumerate(bulk.replace(",", "\n").splitlines()):
            part = _normalize(line)
            if part and part not in seen:
                keys.append((f"GEMINI_API_KEYS[{i}]", part))
                seen.add(part)
    # optional secret files (same as legacy gemini_client)
    for fpath in (
        (os.getenv("GEMINI_API_KEY_FILE") or "").strip(),
        (os.getenv("GOOGLE_API_KEY_FILE") or "").strip(),
        "/run/secrets/gemini_api_key",
        "/run/secrets/GEMINI_API_KEY",
    ):
        if not fpath:
            continue
        try:
            from pathlib import Path as _P

            raw = _P(fpath).read_text(encoding="utf-8")
            seen = {k for _, k in keys}
            for i, line in enumerate(raw.splitlines()):
                val = _normalize(line)
                if val and val not in seen:
                    keys.append((f"{fpath}:{i}", val))
                    seen.add(val)
        except Exception:
            continue
    return keys


def groq_keys() -> list[tuple[str, str]]:
    _ensure_boot_keys()
    assert _BOOT_KEYS is not None
    return list(_BOOT_KEYS["groq"])


def _groq_keys_uncached() -> list[tuple[str, str]]:
    """GROQ_API_KEY + GROQ_API_KEY_0..100 + bulk GROQ_API_KEYS.

    Bulk formats (any one):
      GROQ_API_KEYS=gsk_a,gsk_b,gsk_c
      GROQ_API_KEYS multiline (one key per line)
    """
    keys = collect_env_keys(
        primary_names=("GROQ_API_KEY",),
        numbered_prefix="GROQ_API_KEY_",
        numbered_start=0,
        numbered_end=100,
    )
    bulk = (os.getenv("GROQ_API_KEYS") or "").strip()
    if bulk:
        seen = {k for _, k in keys}
        parts: list[str] = []
        for line in bulk.replace(",", "\n").splitlines():
            part = _normalize(line)
            if part:
                parts.append(part)
        for i, part in enumerate(parts):
            if part in seen:
                continue
            keys.append((f"GROQ_API_KEYS[{i}]", part))
            seen.add(part)
    # optional file
    path = (os.getenv("GROQ_API_KEY_FILE") or "").strip()
    if path:
        try:
            from pathlib import Path as _P
            raw = _P(path).read_text(encoding="utf-8")
            for i, line in enumerate(raw.splitlines()):
                val = _normalize(line)
                if val and val not in {k for _, k in keys}:
                    keys.append((f"{path}:{i}", val))
        except Exception:
            logger.exception("GROQ_API_KEY_FILE unreadable")
    return keys



def qwen_keys() -> list[tuple[str, str]]:
    _ensure_boot_keys()
    assert _BOOT_KEYS is not None
    return list(_BOOT_KEYS["qwen"])


def _qwen_keys_uncached() -> list[tuple[str, str]]:
    """Alibaba DashScope / QwenCloud keys (often sk-ws-...).

    QWEN_API_KEY, DASHSCOPE_API_KEY, QWEN_API_KEY_0..100, QWEN_API_KEYS bulk.
    """
    keys = collect_env_keys(
        primary_names=("QWEN_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_API_KEY_INTL"),
        numbered_prefix="QWEN_API_KEY_",
        numbered_start=0,
        numbered_end=100,
    )
    bulk = (os.getenv("QWEN_API_KEYS") or os.getenv("DASHSCOPE_API_KEYS") or "").strip()
    if bulk:
        seen = {k for _, k in keys}
        for i, line in enumerate(bulk.replace(",", "\n").splitlines()):
            part = _normalize(line)
            if part and part not in seen:
                keys.append((f"QWEN_API_KEYS[{i}]", part))
                seen.add(part)
    return keys


def qwen_available() -> list[tuple[str, str]]:
    failover = _truthy(os.getenv("QWEN_KEY_FAILOVER_ENABLED") or "1")
    return available_keys(qwen_keys(), failover_enabled=failover)


def mark_qwen_cooldown(source: str, *, reason: str = "rate") -> None:
    mark_cooldown(source, env_name="QWEN_KEY_COOLDOWN_SEC", reason=reason)


def gemini_available() -> list[tuple[str, str]]:
    raw = (os.getenv("GEMINI_KEY_FAILOVER_ENABLED") or "").strip()
    failover = _truthy(raw) if raw else True
    return available_keys(gemini_keys(), failover_enabled=failover)


def groq_available() -> list[tuple[str, str]]:
    failover = _truthy(os.getenv("GROQ_KEY_FAILOVER_ENABLED") or "1")
    return available_keys(groq_keys(), failover_enabled=failover)


def mark_gemini_cooldown(source: str, *, reason: str = "rate") -> None:
    mark_cooldown(source, env_name="GEMINI_KEY_COOLDOWN_SEC", reason=reason)


def mark_groq_cooldown(source: str, *, reason: str = "rate") -> None:
    mark_cooldown(source, env_name="GROQ_KEY_COOLDOWN_SEC", reason=reason)


def pool_status() -> dict:
    """Safe diagnostics — counts only, never key values."""
    g = gemini_keys()
    q = groq_keys()
    w = qwen_keys()
    now = time.monotonic()
    return {
        "gemini_keys_total": len(g),
        "gemini_keys_ready": sum(1 for s, _ in g if not is_cooling(s)),
        "gemini_sources": [s for s, _ in g],
        "groq_keys_total": len(q),
        "groq_keys_ready": sum(1 for s, _ in q if not is_cooling(s)),
        "groq_sources": [s for s, _ in q],
        "qwen_keys_total": len(w),
        "qwen_keys_ready": sum(1 for s, _ in w if not is_cooling(s)),
        "qwen_sources": [s for s, _ in w],
    }


__all__ = [
    "gemini_keys",
    "groq_keys",
    "qwen_keys",
    "gemini_available",
    "groq_available",
    "qwen_available",
    "mark_gemini_cooldown",
    "mark_groq_cooldown",
    "mark_qwen_cooldown",
    "mark_cooldown",
    "pool_status",
]
