"""Cluster capacity model for large-scale bot hosting (target: 20k+ bots).

Single-node Docker cannot host 20k processes. Capacity is expressed as:
  cluster_capacity = sum(node_max_bots for healthy nodes)

Defaults (override via env):
  TBE_NODE_MAX_BOTS=250          # hard cap per worker node
  TBE_NODE_MAX_MEMORY_MB=49152   # 48Gi budget accounting
  TBE_BOT_MEMORY_MB=192          # must match TBE_DOCKER_MEMORY
  TBE_CLUSTER_MIN_NODES=1
"""
from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass

logger = logging.getLogger("tbe.hosting.capacity")


def _i(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or str(default)).strip())
    except Exception:
        return default


@dataclass(frozen=True)
class NodeCapacity:
    node_id: str
    max_bots: int
    max_memory_mb: int
    bot_memory_mb: int
    running: int = 0

    @property
    def free_slots(self) -> int:
        by_count = max(0, self.max_bots - self.running)
        by_mem = max(0, (self.max_memory_mb // max(1, self.bot_memory_mb)) - self.running)
        return min(by_count, by_mem)

    @property
    def can_accept(self) -> bool:
        return self.free_slots > 0


def node_id() -> str:
    return (os.environ.get("TBE_NODE_ID") or socket.gethostname() or "node").strip()[:64]


def local_node_capacity(running: int = 0) -> NodeCapacity:
    mem_str = (os.environ.get("TBE_DOCKER_MEMORY") or "192m").strip().lower()
    bot_mb = 192
    if mem_str.endswith("m"):
        try:
            bot_mb = int(mem_str[:-1])
        except Exception:
            bot_mb = 192
    elif mem_str.endswith("g"):
        try:
            bot_mb = int(float(mem_str[:-1]) * 1024)
        except Exception:
            bot_mb = 192
    return NodeCapacity(
        node_id=node_id(),
        max_bots=_i("TBE_NODE_MAX_BOTS", 250),
        max_memory_mb=_i("TBE_NODE_MAX_MEMORY_MB", 48 * 1024),
        bot_memory_mb=_i("TBE_BOT_MEMORY_MB", bot_mb),
        running=max(0, int(running)),
    )


def estimate_nodes_for(target_bots: int = 20_000) -> dict:
    """Planning helper: how many nodes for target concurrent bots."""
    cap = local_node_capacity(0)
    per = max(1, min(cap.max_bots, cap.max_memory_mb // max(1, cap.bot_memory_mb)))
    nodes = (int(target_bots) + per - 1) // per
    return {
        "target_bots": int(target_bots),
        "bots_per_node": per,
        "nodes_required": nodes,
        "node_max_bots": cap.max_bots,
        "bot_memory_mb": cap.bot_memory_mb,
        "note": "20k bots require a worker fleet; one API box cannot run them all",
    }
