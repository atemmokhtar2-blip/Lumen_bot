"""Sandbox supervisor — reap dead bots, enforce lifetime, no zombie fleet."""
from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _docker(args: List[str], timeout: float = 30.0) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, (p.stdout or "")
    except Exception as exc:
        return 1, f"{type(exc).__name__}:{exc}"


def list_managed_containers() -> List[Dict[str, Any]]:
    code, out = _docker(
        [
            "ps",
            "-a",
            "--filter",
            "label=tbe.managed=1",
            "--format",
            '{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Label "tbe.user"}}',
        ]
    )
    rows: List[Dict[str, Any]] = []
    if code != 0:
        return rows
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append(
                {
                    "id": parts[0],
                    "name": parts[1],
                    "status": parts[2],
                    "user": parts[3] if len(parts) > 3 else "",
                }
            )
    return rows


def reap_exited(*, remove: bool = True) -> int:
    n = 0
    for c in list_managed_containers():
        st = (c.get("status") or "").lower()
        if st.startswith("exited") or st.startswith("dead"):
            if remove:
                _docker(["rm", "-f", c["id"]])
            n += 1
    return n


def enforce_max_lifetime() -> int:
    max_sec = int((os.environ.get("TBE_BOT_MAX_LIFETIME_SEC") or "0").strip() or "0")
    if max_sec <= 0:
        return 0
    killed = 0
    code, out = _docker(
        [
            "ps",
            "--filter",
            "label=tbe.managed=1",
            "--format",
            "{{.ID}}",
        ]
    )
    if code != 0:
        return 0
    for cid in (out or "").splitlines():
        cid = cid.strip()
        if not cid:
            continue
        c2, started = _docker(["inspect", "-f", "{{.State.StartedAt}}", cid])
        if c2 != 0:
            continue
        try:
            p = subprocess.run(
                ["date", "-d", started.strip(), "+%s"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if p.returncode != 0:
                continue
            started_ts = int(p.stdout.strip())
            if time.time() - started_ts > max_sec:
                _docker(["rm", "-f", cid])
                killed += 1
                logger.warning("supervisor killed over-lifetime container %s", cid[:12])
        except Exception:
            continue
    return killed


def supervisor_tick() -> Dict[str, int]:
    return {
        "reaped": reap_exited(remove=True),
        "lifetime_killed": enforce_max_lifetime(),
    }
