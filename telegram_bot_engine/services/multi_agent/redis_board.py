"""Durable multi-agent state across process restarts."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional

from .blackboard import (
    BlackboardStore,
    FileBlackboard,
    LayeredBlackboard,
    MemoryBlackboard,
)
from .state import AgentState, AgentStatus

logger = logging.getLogger(__name__)

_RESUMABLE = frozenset({
    AgentStatus.PENDING.value,
    AgentStatus.ROUTING.value,
    AgentStatus.PLANNING.value,
    AgentStatus.BUILDING.value,
    AgentStatus.QA.value,
    AgentStatus.AWAITING_CONFIRMATION.value,
    AgentStatus.FAILED.value,
})

_PREFIX = (os.environ.get("MULTI_AGENT_REDIS_PREFIX") or "maestro:ma:").strip() or "maestro:ma:"
_TTL = int(os.environ.get("MULTI_AGENT_REDIS_TTL_SEC") or str(7 * 24 * 3600))


def redis_board_enabled() -> bool:
    if (os.environ.get("MULTI_AGENT_REDIS_BOARD") or "1").strip().lower() in {
        "0", "false", "no", "off",
    }:
        return False
    return bool((os.environ.get("JOB_REDIS_URL") or os.environ.get("REDIS_URL") or "").strip())


def _client():
    import redis
    url = (os.environ.get("JOB_REDIS_URL") or os.environ.get("REDIS_URL") or "").strip()
    if not url:
        raise RuntimeError("REDIS_URL required")
    return redis.Redis.from_url(url, decode_responses=True)


def _sk(state_id: str) -> str:
    safe = "".join(c for c in state_id if c.isalnum() or c in "-_")[:80]
    return f"{_PREFIX}state:{safe}"


def _ik() -> str:
    return f"{_PREFIX}resumable"


def _uk(user_id: int) -> str:
    return f"{_PREFIX}user:{int(user_id)}"


def _stream_key(state_id: str) -> str:
    safe = "".join(c for c in state_id if c.isalnum() or c in "-_")[:80]
    return f"{_PREFIX}stream:{safe}"


def _events_index() -> str:
    return f"{_PREFIX}streams"


def append_agent_event(
    state_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> str | None:
    """Append-only Redis Stream event for multi-agent transitions (resumability).

    Best-effort: never raises to callers. Returns stream entry id or None.
    """
    if not state_id or not redis_board_enabled():
        return None
    if (os.environ.get("MULTI_AGENT_EVENT_STREAM") or "1").strip().lower() in {
        "0", "false", "no", "off",
    }:
        return None
    try:
        r = get_redis_mirror().conn()
        fields = {
            "type": str(event_type or "event")[:64],
            "ts": str(time.time()),
            "payload": json.dumps(payload or {}, ensure_ascii=False)[:8000],
        }
        entry_id = r.xadd(
            _stream_key(state_id),
            fields,
            maxlen=int(os.environ.get("MULTI_AGENT_STREAM_MAXLEN") or "500"),
            approximate=True,
        )
        # Track active streams for boot scan
        r.sadd(_events_index(), state_id)
        r.expire(_events_index(), _TTL)
        r.expire(_stream_key(state_id), _TTL)
        return str(entry_id) if entry_id else None
    except Exception:
        logger.debug("append_agent_event failed id=%s", state_id, exc_info=True)
        return None


class RedisMirror:
    def __init__(self) -> None:
        self._c = None
        self._lock = threading.RLock()

    def conn(self):
        if self._c is None:
            self._c = _client()
        return self._c

    def put(self, state: AgentState) -> None:
        if not redis_board_enabled():
            return
        try:
            r = self.conn()
            pipe = r.pipeline()
            pipe.set(_sk(state.state_id), json.dumps(state.to_dict(), ensure_ascii=False), ex=_TTL)
            if state.status in _RESUMABLE:
                pipe.zadd(_ik(), {state.state_id: float(state.updated_at or time.time())})
            else:
                pipe.zrem(_ik(), state.state_id)
            if state.user_id:
                pipe.set(_uk(int(state.user_id)), state.state_id, ex=_TTL)
            pipe.execute()
            # Durable event log for crash recovery / audit
            append_agent_event(
                state.state_id,
                "state_put",
                {
                    "status": state.status,
                    "attempts": int(getattr(state, "attempts", 0) or 0),
                    "user_id": int(getattr(state, "user_id", 0) or 0),
                    "qa_passed": bool(getattr(state, "qa_passed", False)),
                    "build_success": bool(getattr(state, "build_success", False)),
                },
            )
        except Exception:
            logger.warning("redis mirror put failed id=%s", state.state_id, exc_info=True)

    def get(self, state_id: str) -> Optional[AgentState]:
        if not redis_board_enabled():
            return None
        try:
            raw = self.conn().get(_sk(state_id))
            if not raw:
                return None
            return AgentState.from_dict(json.loads(raw))
        except Exception:
            logger.warning("redis mirror get failed", exc_info=True)
            return None

    def list_resumable(self, *, limit: int = 50) -> list[str]:
        if not redis_board_enabled():
            return []
        try:
            return [str(x) for x in self.conn().zrevrange(_ik(), 0, max(0, min(limit, 200) - 1))]
        except Exception:
            logger.warning("redis list_resumable failed", exc_info=True)
            return []


_mirror: RedisMirror | None = None
_mlock = threading.Lock()


def get_redis_mirror() -> RedisMirror:
    global _mirror
    with _mlock:
        if _mirror is None:
            _mirror = RedisMirror()
        return _mirror


class RedisLayeredBlackboard(BlackboardStore):
    def __init__(self) -> None:
        self.inner = LayeredBlackboard()
        self.mirror = get_redis_mirror()

    def put(self, state: AgentState) -> AgentState:
        out = self.inner.put(state)
        self.mirror.put(out)
        # Flag for worker boot / auto-enqueue (deduped in enqueue_pending_resumes)
        if out.status in _RESUMABLE and redis_board_enabled():
            try:
                if (os.environ.get("MULTI_AGENT_AUTO_ENQUEUE_RESUME") or "1").strip().lower() not in {
                    "0", "false", "no", "off",
                }:
                    # Only park marker — actual enqueue is batched by worker/boot
                    r = self.mirror.conn()
                    r.sadd(f"{_PREFIX}needs_resume", out.state_id)
                    r.expire(f"{_PREFIX}needs_resume", _TTL)
            except Exception:
                pass
        return out

    def get(self, state_id: str) -> Optional[AgentState]:
        s = self.inner.get(state_id)
        if s is not None:
            return s
        remote = self.mirror.get(state_id)
        if remote is not None:
            try:
                self.inner.put(remote)
            except Exception:
                pass
            return remote
        return None

    def latest_for_user(self, user_id: int) -> Optional[AgentState]:
        s = self.inner.latest_for_user(user_id)
        if s is not None:
            return s
        if not redis_board_enabled():
            return None
        try:
            sid = self.mirror.conn().get(_uk(int(user_id)))
            return self.get(str(sid)) if sid else None
        except Exception:
            return None

    def list_ids(self, *, limit: int = 100) -> list[str]:
        ids = self.inner.list_ids(limit=limit)
        return ids or self.mirror.list_resumable(limit=limit)


def list_resumable_state_ids(*, limit: int = 50) -> list[str]:
    ids = get_redis_mirror().list_resumable(limit=limit)
    if ids:
        return ids
    try:
        from .blackboard import get_blackboard
        board = get_blackboard()
        out = []
        for sid in board.list_ids(limit=limit):
            st = board.get(sid)
            if st and st.status in _RESUMABLE:
                out.append(sid)
        return out
    except Exception:
        return []


def resume_interrupted_state(
    state_id: str,
    *,
    user_id: int = 0,
    work_dir: str | None = None,
) -> AgentState:
    from .blackboard import get_blackboard
    from .orchestrator import Orchestrator

    board = get_blackboard()
    state = board.get(state_id)
    if state is None:
        failed = AgentState(status=AgentStatus.FAILED.value)
        failed.final_message = f"state_not_found:{state_id}"
        return failed
    if user_id and int(state.user_id or 0) not in {0, int(user_id)}:
        state.final_message = "user_mismatch"
        return state
    if state.status in {
        AgentStatus.DELIVERED.value,
        AgentStatus.CANCELLED.value,
        AgentStatus.PASSED.value,
    }:
        return state
    ctx: dict[str, Any] = {}
    if work_dir:
        ctx["work_dir"] = work_dir
    elif (state.extensions or {}).get("work_dir"):
        ctx["work_dir"] = state.extensions["work_dir"]
    return Orchestrator(board=board).run(state, context=ctx)


def scan_and_resume(*, limit: int = 10) -> list[dict[str, Any]]:
    results = []
    for sid in list_resumable_state_ids(limit=limit):
        try:
            st = resume_interrupted_state(sid)
            results.append({
                "state_id": sid,
                "status": st.status,
                "ok": bool(st.qa_passed or st.build_success),
                "path": st.generated_path or "",
            })
        except Exception as exc:
            results.append({"state_id": sid, "error": f"{type(exc).__name__}:{exc}"})
    return results


def enqueue_resume_job(state_id: str, *, tenant_id: str = "platform") -> dict[str, Any] | None:
    if not redis_board_enabled():
        return None
    try:
        from b2b_platform.task_queue import enqueue_job
        return enqueue_job(
            tenant_id=tenant_id,
            kind="multi_agent_resume",
            input_data={"state_id": state_id},
            message=f"resume {state_id}",
        )
    except Exception:
        logger.warning("enqueue_resume_job failed", exc_info=True)
        return None


def enqueue_pending_resumes(*, limit: int = 20, tenant_id: str = "platform") -> list[dict[str, Any]]:
    """Enqueue RQ resume jobs for interrupted multi-agent states (worker boot).

    Dedupes via Redis set maestro:ma:resume_queued so the same state is not
    spammed into the queue on every worker restart.
    """
    results: list[dict[str, Any]] = []
    if not redis_board_enabled():
        # File-board only: attempt limited inline resume (dev/single-node)
        if (os.environ.get("MULTI_AGENT_INLINE_RESUME_ON_BOOT") or "").strip().lower() in {
            "1", "true", "yes", "on",
        }:
            return scan_and_resume(limit=limit)
        return results

    try:
        r = get_redis_mirror().conn()
        queued_key = f"{_PREFIX}resume_queued"
        needs_key = f"{_PREFIX}needs_resume"
        # Merge explicit needs_resume markers + zset index
        candidates: list[str] = []
        try:
            candidates.extend(str(x) for x in r.smembers(needs_key) or [])
        except Exception:
            pass
        candidates.extend(list_resumable_state_ids(limit=limit))
        # unique preserve order
        seen: set[str] = set()
        ordered: list[str] = []
        for sid in candidates:
            if sid and sid not in seen:
                seen.add(sid)
                ordered.append(sid)
        for sid in ordered[: max(1, min(limit, 50))]:
            try:
                if r.sismember(queued_key, sid):
                    results.append({"state_id": sid, "skipped": "already_queued"})
                    continue
                job = enqueue_resume_job(sid, tenant_id=tenant_id)
                if job:
                    r.sadd(queued_key, sid)
                    r.expire(queued_key, min(_TTL, 86400))
                    try:
                        r.srem(needs_key, sid)
                    except Exception:
                        pass
                    results.append({"state_id": sid, "enqueued": True, "job": job})
                else:
                    results.append({"state_id": sid, "enqueued": False})
            except Exception as exc:
                results.append({"state_id": sid, "error": f"{type(exc).__name__}:{exc}"})
    except Exception:
        logger.warning("enqueue_pending_resumes failed", exc_info=True)
    return results


__all__ = [
    "RedisMirror",
    "RedisLayeredBlackboard",
    "redis_board_enabled",
    "get_redis_mirror",
    "list_resumable_state_ids",
    "resume_interrupted_state",
    "scan_and_resume",
    "enqueue_resume_job",
    "enqueue_pending_resumes",
    "append_agent_event",
]
