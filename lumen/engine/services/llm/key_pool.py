"""Shared API-key pool with cooldown + ordered failover.

Gemini: GEMINI_API_KEY / GOOGLE_* aliases + GEMINI_API_KEY_0 .. GEMINI_API_KEY_150
Groq:   GROQ_API_KEY + GROQ_API_KEY_0..100 + GROQ_API_KEYS
Qwen:   QWEN_API_KEY / DASHSCOPE_API_KEY + QWEN_API_KEY_0..100 + QWEN_API_KEYS (sk-ws-)

When a key hits auth/rate limits it is cooled down; the next ready key is used
until the pool is exhausted, then the least-cooled key is retried.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Iterable

logger = logging.getLogger(__name__)

# source_name → monotonic deadline
_COOLDOWN_UNTIL: dict[str, float] = {}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


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


def mark_cooldown(source: str, *, seconds: float | None = None, env_name: str = "KEY_COOLDOWN_SEC") -> None:
    sec = seconds if seconds is not None else cooldown_seconds(env_name, 60.0)
    if sec <= 0:
        return
    _COOLDOWN_UNTIL[source] = time.monotonic() + sec
    logger.warning("key cooldown source=%s for %.0fs", source, sec)


def is_cooling(source: str) -> bool:
    return _COOLDOWN_UNTIL.get(source, 0.0) > time.monotonic()


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
    """Keys not in cooldown; if all cooling, return first as last resort."""
    if not all_keys:
        return []
    if not failover_enabled or len(all_keys) <= 1:
        return all_keys[:1]
    ready = [(s, k) for s, k in all_keys if not is_cooling(s)]
    if ready:
        return ready
    # all cooling — pick the one that cools down soonest
    def _until(source: str) -> float:
        return _COOLDOWN_UNTIL.get(source, 0.0)

    ordered = sorted(all_keys, key=lambda sk: _until(sk[0]))
    return ordered[:1]


def gemini_keys() -> list[tuple[str, str]]:
    """GEMINI_API_KEY (+ aliases) and GEMINI_API_KEY_0 .. _150."""
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
    if keys:
        return keys
    # optional secret files (same as legacy gemini_client)
    for path in (
        (os.getenv("GEMINI_API_KEY_FILE") or "").strip(),
        (os.getenv("GOOGLE_API_KEY_FILE") or "").strip(),
        "/run/secrets/gemini_api_key",
        "/run/secrets/GEMINI_API_KEY",
    ):
        if not path:
            continue
        try:
            from pathlib import Path

            raw = Path(path).read_text(encoding="utf-8")
            val = _normalize(raw.splitlines()[0] if raw else "")
            if val:
                return [(path, val)]
        except Exception:
            continue
    return []


def groq_keys() -> list[tuple[str, str]]:
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


def mark_qwen_cooldown(source: str) -> None:
    mark_cooldown(source, env_name="QWEN_KEY_COOLDOWN_SEC")

def gemini_available() -> list[tuple[str, str]]:
    raw = (os.getenv("GEMINI_KEY_FAILOVER_ENABLED") or "").strip()
    failover = _truthy(raw) if raw else True
    return available_keys(gemini_keys(), failover_enabled=failover)


def groq_available() -> list[tuple[str, str]]:
    failover = _truthy(os.getenv("GROQ_KEY_FAILOVER_ENABLED") or "1")
    return available_keys(groq_keys(), failover_enabled=failover)


def mark_gemini_cooldown(source: str) -> None:
    mark_cooldown(source, env_name="GEMINI_KEY_COOLDOWN_SEC")


def mark_groq_cooldown(source: str) -> None:
    mark_cooldown(source, env_name="GROQ_KEY_COOLDOWN_SEC")


def pool_status() -> dict:
    """Safe diagnostics — counts only, never key values."""
    g = gemini_keys()
    q = groq_keys()
    w = qwen_keys()
    now = time.monotonic()
    return {
        "gemini_keys_total": len(g),
        "gemini_keys_ready": sum(1 for s, _ in g if _COOLDOWN_UNTIL.get(s, 0.0) <= now),
        "gemini_sources": [s for s, _ in g],
        "groq_keys_total": len(q),
        "groq_keys_ready": sum(1 for s, _ in q if _COOLDOWN_UNTIL.get(s, 0.0) <= now),
        "groq_sources": [s for s, _ in q],
        "qwen_keys_total": len(w),
        "qwen_keys_ready": sum(1 for s, _ in w if _COOLDOWN_UNTIL.get(s, 0.0) <= now),
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
