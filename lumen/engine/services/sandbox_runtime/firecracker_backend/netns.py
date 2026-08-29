"""Network namespace helpers for Firecracker VMs."""
from __future__ import annotations

import logging
import os

from .process_util import _run

logger = logging.getLogger(__name__)

def _ensure_netns(name: str) -> str:
    """Ensure a network namespace exists; return path for jailer --netns."""
    safe = "".join(c for c in name if c.isalnum() or c in "-_")[:48] or "fc-default"
    ns_path = Path("/var/run/netns") / safe
    if ns_path.exists():
        return str(ns_path)
    if not shutil.which("ip"):
        raise RuntimeError("iproute2_missing_for_netns")
    Path("/var/run/netns").mkdir(parents=True, exist_ok=True)
    code, _, err = _run(["ip", "netns", "add", safe], timeout=15)
    if code != 0 and not ns_path.exists():
        raise RuntimeError(f"netns_create_failed:{err[:200]}")
    return str(ns_path)


