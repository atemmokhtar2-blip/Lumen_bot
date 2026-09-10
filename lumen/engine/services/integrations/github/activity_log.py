"""Per-user GitHub activity log — trust surface for connection lifecycle.

Events (examples):
  connected | disconnected | repo_imported | push | pull_request | branch
  install_updated | token_refresh_failed

Storage: Redis list (preferred) with in-process fallback.
Never stores tokens or secrets — detail is public metadata only.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any
from lumen.platform.redis_client import connect_redis_url

logger = logging.getLogger("lumen.github.activity_log")

_PREFIX = "lumen:gh:activity:"
_MAX = int(os.getenv("GITHUB_ACTIVITY_LOG_MAX") or "50")
_lock = threading.Lock()
_local: dict[int, list[dict[str, Any]]] = {}

# Events that also go to platform security_events
_SECURITY_MIRROR = frozenset({"connected", "disconnected", "push", "pull_request"})


def _redis():
    try:
        from lumen.platform.runtime_config import redis_url as _ru

        url = (_ru() or "").strip()
    except Exception:
        url = (os.getenv("REDIS_URL") or os.getenv("JOB_REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        r = connect_redis_url(
            url,
            decode_responses=True,
            socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT") or "2"),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT") or "3"),
        )
        r.ping()
        return r
    except Exception:
        return None


def _scrub_detail(detail: dict[str, Any] | None) -> dict[str, Any]:
    if not detail:
        return {}
    out: dict[str, Any] = {}
    blocked = {"token", "pat", "password", "secret", "authorization", "ciphertext"}
    for k, v in detail.items():
        key = str(k).lower()
        if key in blocked or "token" in key or "secret" in key:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            s = str(v) if v is not None else ""
            if len(s) > 200:
                s = s[:200] + "…"
            out[str(k)[:40]] = s if not isinstance(v, bool) else v
            if isinstance(v, (int, float, bool)) and not isinstance(v, bool):
                out[str(k)[:40]] = v
            elif isinstance(v, bool):
                out[str(k)[:40]] = v
            else:
                out[str(k)[:40]] = s
        elif isinstance(v, (list, dict)):
            try:
                raw = json.dumps(v, ensure_ascii=False)[:200]
            except Exception:
                raw = str(type(v).__name__)
            out[str(k)[:40]] = raw
    return out


def record(
    user_id: int,
    event: str,
    *,
    detail: dict[str, Any] | None = None,
    severity: str = "info",
) -> None:
    """Append one activity row for this Telegram user."""
    uid = int(user_id or 0)
    ev = (event or "").strip().lower()[:40]
    if uid <= 0 or not ev:
        return
    row = {
        "ts": time.time(),
        "event": ev,
        "detail": _scrub_detail(detail),
        "severity": (severity or "info")[:16],
    }
    payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))

    r = _redis()
    if r is not None:
        try:
            key = f"{_PREFIX}{uid}"
            r.lpush(key, payload)
            r.ltrim(key, 0, max(9, _MAX - 1))
            r.expire(key, 90 * 24 * 3600)
        except Exception:
            logger.debug("activity redis write failed", exc_info=True)
            r = None
    if r is None:
        with _lock:
            bucket = _local.setdefault(uid, [])
            bucket.insert(0, row)
            del bucket[_MAX:]

    if ev in _SECURITY_MIRROR:
        try:
            from lumen.platform.security_events import emit

            emit(
                f"github.{ev}",
                severity=severity if severity in {"info", "warning", "critical"} else "info",
                actor=f"tg:{uid}",
                detail=row["detail"],
            )
        except Exception:
            pass


def list_recent(user_id: int, *, limit: int = 15) -> list[dict[str, Any]]:
    """Newest-first activity rows (no secrets)."""
    uid = int(user_id or 0)
    lim = max(1, min(int(limit or 15), _MAX))
    if uid <= 0:
        return []

    r = _redis()
    if r is not None:
        try:
            raw = r.lrange(f"{_PREFIX}{uid}", 0, lim - 1) or []
            out: list[dict[str, Any]] = []
            for item in raw:
                try:
                    out.append(json.loads(item))
                except Exception:
                    continue
            return out
        except Exception:
            logger.debug("activity redis read failed", exc_info=True)

    with _lock:
        return list(_local.get(uid, [])[:lim])


def format_activity_ar(user_id: int, *, limit: int = 10) -> str:
    """Human-readable Arabic summary for Telegram."""
    rows = list_recent(user_id, limit=limit)
    if not rows:
        return "لا يوجد نشاط مسجّل بعد لهذا الاتصال."

    labels = {
        "connected": "تم الاتصال",
        "disconnected": "فصل الاتصال",
        "repo_imported": "استيراد مستودع",
        "push": "دفع (push)",
        "pull_request": "فتح Pull Request",
        "branch": "إنشاء فرع",
        "install_updated": "تحديث التثبيت",
        "list_repos": "تحديث قائمة المستودعات",
        "token_refresh_failed": "فشل تجديد التوكن",
    }
    lines: list[str] = ["📋 *سجل نشاط GitHub*", ""]
    for row in rows:
        ev = str(row.get("event") or "")
        label = labels.get(ev, ev)
        ts = float(row.get("ts") or 0)
        when = _relative_ar(ts)
        det = row.get("detail") or {}
        extra = ""
        if det.get("login"):
            extra = f" · @{det['login']}"
        elif det.get("full_name"):
            extra = f" · `{det['full_name']}`"
        elif det.get("repo"):
            extra = f" · `{det['repo']}`"
        lines.append(f"• {label}{extra} — {when}")
    return "\n".join(lines)


def _relative_ar(ts: float) -> str:
    if ts <= 0:
        return "—"
    delta = max(0, int(time.time() - ts))
    if delta < 60:
        return "الآن"
    if delta < 3600:
        return f"منذ {delta // 60} د"
    if delta < 86400:
        return f"منذ {delta // 3600} س"
    return f"منذ {delta // 86400} ي"


__all__ = ["record", "list_recent", "format_activity_ar"]
