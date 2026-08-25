"""Worker fleet registry (Postgres).

Each worker process registers and heartbeats. The scheduler/claim logic prefers
nodes with free capacity. Stale workers (no heartbeat) are marked offline.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("tbe.hosting.fleet")


@dataclass
class WorkerRecord:
    node_id: str
    hostname: str
    status: str
    max_bots: int
    running_bots: int
    max_memory_mb: int
    bot_memory_mb: int
    version: str
    last_heartbeat: float
    free_slots: int = 0


def _node_id() -> str:
    return (os.environ.get("TBE_NODE_ID") or socket.gethostname() or "node").strip()[:64]


class FleetRegistry:
    def __init__(self) -> None:
        from lumen.engine.services.hosting.pg_control_plane import migrate, is_postgres
        if not is_postgres():
            raise RuntimeError("fleet requires Postgres TBE_DATABASE_URL")
        migrate()

    def _connect(self):
        from lumen.engine.services.hosting.pg_control_plane import connect
        return connect()

    def register(
        self,
        *,
        max_bots: int | None = None,
        max_memory_mb: int | None = None,
        bot_memory_mb: int | None = None,
        version: str = "1",
        labels: dict | None = None,
    ) -> WorkerRecord:
        from lumen.engine.services.hosting.capacity import local_node_capacity
        cap = local_node_capacity(0)
        nid = _node_id()
        now = time.time()
        mb = int(max_bots if max_bots is not None else cap.max_bots)
        mm = int(max_memory_mb if max_memory_mb is not None else cap.max_memory_mb)
        bm = int(bot_memory_mb if bot_memory_mb is not None else cap.bot_memory_mb)
        host = socket.gethostname()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tbe_workers (
                      node_id, hostname, status, max_bots, running_bots,
                      max_memory_mb, bot_memory_mb, version, labels_json,
                      last_heartbeat, registered_at, updated_at
                    ) VALUES (%s,%s,'online',%s,0,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (node_id) DO UPDATE SET
                      hostname=EXCLUDED.hostname,
                      status='online',
                      max_bots=EXCLUDED.max_bots,
                      max_memory_mb=EXCLUDED.max_memory_mb,
                      bot_memory_mb=EXCLUDED.bot_memory_mb,
                      version=EXCLUDED.version,
                      labels_json=EXCLUDED.labels_json,
                      last_heartbeat=EXCLUDED.last_heartbeat,
                      updated_at=EXCLUDED.updated_at
                    """,
                    (
                        nid, host, mb, mm, bm, version,
                        json.dumps(labels or {}, ensure_ascii=False),
                        now, now, now,
                    ),
                )
            conn.commit()
        return WorkerRecord(
            node_id=nid, hostname=host, status="online",
            max_bots=mb, running_bots=0, max_memory_mb=mm, bot_memory_mb=bm,
            version=version, last_heartbeat=now, free_slots=mb,
        )

    def heartbeat(self, running_bots: int = 0) -> None:
        nid = _node_id()
        now = time.time()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tbe_workers
                    SET last_heartbeat=%s, running_bots=%s, status='online', updated_at=%s
                    WHERE node_id=%s
                    """,
                    (now, int(running_bots), now, nid),
                )
            conn.commit()

    def mark_offline(self, node_id: str | None = None) -> None:
        nid = node_id or _node_id()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE tbe_workers SET status='offline', updated_at=%s WHERE node_id=%s",
                    (time.time(), nid),
                )
            conn.commit()

    def sweep_stale(self, stale_seconds: float | None = None) -> int:
        stale = float(stale_seconds or os.environ.get("TBE_WORKER_STALE_SECONDS") or 90)
        cutoff = time.time() - stale
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tbe_workers SET status='offline', updated_at=%s
                    WHERE status='online' AND last_heartbeat < %s
                    """,
                    (time.time(), cutoff),
                )
                n = cur.rowcount or 0
            conn.commit()
        return int(n)

    def list_online(self) -> list[WorkerRecord]:
        self.sweep_stale()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT node_id, hostname, status, max_bots, running_bots,
                           max_memory_mb, bot_memory_mb, version, last_heartbeat
                    FROM tbe_workers WHERE status='online'
                    ORDER BY (max_bots - running_bots) DESC
                    """
                )
                rows = cur.fetchall()
        out = []
        for r in rows:
            free = max(0, int(r[3]) - int(r[4]))
            out.append(WorkerRecord(
                node_id=r[0], hostname=r[1], status=r[2],
                max_bots=int(r[3]), running_bots=int(r[4]),
                max_memory_mb=int(r[5]), bot_memory_mb=int(r[6]),
                version=str(r[7] or ""), last_heartbeat=float(r[8] or 0),
                free_slots=free,
            ))
        return out

    def cluster_free_slots(self) -> int:
        return sum(w.free_slots for w in self.list_online())

    def cluster_summary(self) -> dict:
        online = self.list_online()
        return {
            "online_nodes": len(online),
            "free_slots": sum(w.free_slots for w in online),
            "running_bots": sum(w.running_bots for w in online),
            "max_bots": sum(w.max_bots for w in online),
            "nodes": [
                {"node_id": w.node_id, "free": w.free_slots, "running": w.running_bots, "max": w.max_bots}
                for w in online
            ],
        }
