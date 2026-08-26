"""Event bus for long-running / reactive agents.

Backends:
  1) Redis pub/sub when REDIS_URL is set (horizontal)
  2) In-process threading handlers (dev / single node)

Event names (examples):
  job.failed, job.completed, generation.started, generation.finished
  github.pr.opened, github.issue.commented, schedule.tick, agent.resume
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], None]


@dataclass
class Event:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = field(default_factory=time.time)
    source: str = "lumen"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "name": self.name,
            "payload": dict(self.payload or {}),
            "ts": self.ts,
            "source": self.source,
        }


class EventBus:
    def __init__(self) -> None:
        self._local: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()
        self._redis = None
        self._listener_started = False
        self._channel = (os.getenv("LUMEN_EVENTS_CHANNEL") or "lumen:events").strip()

    def _redis_client(self):
        if self._redis is not None:
            return self._redis
        url = (os.getenv("REDIS_URL") or os.getenv("REDIS_URI") or "").strip()
        if not url:
            return None
        try:
            import redis
            self._redis = redis.Redis.from_url(url, decode_responses=True)
            self._redis.ping()
            return self._redis
        except Exception:
            logger.warning("Redis event bus unavailable", exc_info=True)
            self._redis = False  # type: ignore
            return None

    def subscribe(self, event_name: str, handler: Handler) -> None:
        with self._lock:
            self._local[event_name].append(handler)
            self._local["*"].append(handler) if event_name == "*" else None
        self._ensure_redis_listener()

    def on(self, event_name: str) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            self.subscribe(event_name, fn)
            return fn
        return deco

    def emit(self, event_name: str, payload: dict[str, Any] | None = None, *, source: str = "lumen") -> Event:
        ev = Event(name=event_name, payload=dict(payload or {}), source=source)
        # local dispatch
        self._dispatch_local(ev)
        # redis publish for other nodes
        client = self._redis_client()
        if client:
            try:
                client.publish(self._channel, json.dumps(ev.to_dict(), ensure_ascii=False))
            except Exception:
                logger.exception("event publish failed")
        return ev

    def _dispatch_local(self, ev: Event) -> None:
        handlers: list[Handler] = []
        with self._lock:
            handlers.extend(self._local.get(ev.name) or [])
            handlers.extend(self._local.get("*") or [])
        data = ev.to_dict()
        for h in handlers:
            try:
                h(data)
            except Exception:
                logger.exception("event handler failed name=%s", ev.name)

    def _ensure_redis_listener(self) -> None:
        if self._listener_started:
            return
        client = self._redis_client()
        if not client:
            return
        self._listener_started = True

        def _loop() -> None:
            try:
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(self._channel)
                for message in pubsub.listen():
                    if not message or message.get("type") != "message":
                        continue
                    try:
                        data = json.loads(message.get("data") or "{}")
                        # Avoid double-handling events emitted on this process:
                        # still dispatch — handlers should be idempotent.
                        name = str(data.get("name") or "")
                        if not name:
                            continue
                        ev = Event(
                            name=name,
                            payload=dict(data.get("payload") or {}),
                            event_id=str(data.get("event_id") or uuid.uuid4().hex),
                            ts=float(data.get("ts") or time.time()),
                            source=str(data.get("source") or "redis"),
                        )
                        # only local handlers (do not re-publish)
                        self._dispatch_local(ev)
                    except Exception:
                        logger.exception("event listen parse failed")
            except Exception:
                logger.exception("event redis listener died")

        threading.Thread(target=_loop, name="lumen-events", daemon=True).start()


_BUS: EventBus | None = None
_BUS_LOCK = threading.Lock()


def get_bus() -> EventBus:
    global _BUS
    with _BUS_LOCK:
        if _BUS is None:
            _BUS = EventBus()
        return _BUS


def emit(event_name: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> Event:
    return get_bus().emit(event_name, payload, **kwargs)


def subscribe(event_name: str, handler: Handler) -> None:
    get_bus().subscribe(event_name, handler)


def on(event_name: str) -> Callable[[Handler], Handler]:
    return get_bus().on(event_name)


__all__ = ["Event", "EventBus", "emit", "get_bus", "on", "subscribe"]
