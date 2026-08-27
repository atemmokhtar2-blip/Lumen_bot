"""Sandbox supervisor — reap, lifetime, usage heartbeats with real labels/stats."""
from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
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
    """List managed containers with full label map via inspect."""
    code, out = _docker(
        ["ps", "-a", "--filter", "label=tbe.managed=1", "--format", "{{.ID}}"]
    )
    rows: List[Dict[str, Any]] = []
    if code != 0:
        return rows
    for cid in (out or "").splitlines():
        cid = cid.strip()
        if not cid:
            continue
        c2, insp = _docker(
            [
                "inspect",
                "--format",
                '{{json .}}',
                cid,
            ],
            timeout=15.0,
        )
        labels: Dict[str, str] = {}
        name = ""
        status = ""
        if c2 == 0 and insp.strip():
            try:
                import json
                data = json.loads(insp)
                labels = {str(k): str(v) for k, v in (data.get("Config", {}).get("Labels") or {}).items()}
                name = (data.get("Name") or "").lstrip("/")
                status = (data.get("State", {}) or {}).get("Status") or ""
            except Exception:
                pass
        if not labels:
            # fallback format
            c3, line = _docker(
                [
                    "ps", "-a", "--filter", f"id={cid}",
                    "--format",
                    '{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Label "tbe.tenant_id"}}\t{{.Label "tbe.bot_id"}}\t{{.Label "tbe.user"}}',
                ]
            )
            if c3 == 0 and line.strip():
                parts = line.strip().split("\t")
                name = parts[1] if len(parts) > 1 else ""
                status = parts[2] if len(parts) > 2 else ""
                if len(parts) > 3 and parts[3]:
                    labels["tbe.tenant_id"] = parts[3]
                if len(parts) > 4 and parts[4]:
                    labels["tbe.bot_id"] = parts[4]
                if len(parts) > 5 and parts[5]:
                    labels["tbe.user"] = parts[5]
        rows.append(
            {
                "id": cid,
                "name": name,
                "status": status,
                "labels": labels,
                "user": labels.get("tbe.user") or "",
                "tenant_id": labels.get("tbe.tenant_id") or "",
                "bot_id": labels.get("tbe.bot_id") or "",
            }
        )
    return rows


def reap_exited(*, remove: bool = True) -> int:
    n = 0
    for c in list_managed_containers():
        st = (c.get("status") or "").lower()
        if st.startswith("exited") or st.startswith("dead") or st == "exited":
            if remove:
                _docker(["rm", "-f", c["id"]])
            n += 1
    return n


def enforce_max_lifetime() -> int:
    max_sec = int((os.environ.get("TBE_BOT_MAX_LIFETIME_SEC") or "0").strip() or "0")
    if max_sec <= 0:
        return 0
    killed = 0
    for c in list_managed_containers():
        cid = c.get("id") or ""
        if not cid:
            continue
        c2, started = _docker(["inspect", "-f", "{{.State.StartedAt}}", cid])
        if c2 != 0:
            continue
        try:
            p = subprocess.run(
                ["date", "-d", started.strip(), "+%s"],
                capture_output=True, text=True, timeout=5, check=False,
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
    reaped = reap_exited(remove=True)
    lifetime_killed = enforce_max_lifetime()
    fc_reaped = reap_exited_firecracker(remove=True)
    fc_lifetime = enforce_max_lifetime_firecracker()
    heartbeats = 0
    try:
        from lumen.engine.services.usage.heartbeat import emit_host_heartbeat
        for c in list_managed_containers():
            st = (c.get("status") or "").lower()
            if st and st not in {"running", "up"} and not st.startswith("up"):
                continue
            labels = c.get("labels") if isinstance(c.get("labels"), dict) else {}
            tenant_id = str(
                labels.get("tbe.tenant_id") or c.get("tenant_id") or ""
            ).strip()
            bot_id = str(
                labels.get("tbe.bot_id") or c.get("bot_id") or c.get("name") or c.get("id") or ""
            ).strip()[:120]
            if not tenant_id or not bot_id:
                continue
            r = emit_host_heartbeat(
                tenant_id=tenant_id,
                bot_id=bot_id,
                container_id=str(c.get("id") or ""),
            )
            if r.get("ok"):
                heartbeats += 1
    except Exception:
        logger.debug("usage heartbeat skipped", exc_info=True)
    return {
        "reaped": reaped,
        "lifetime_killed": lifetime_killed,
        "fc_reaped": fc_reaped,
        "fc_lifetime_killed": fc_lifetime,
        "heartbeats": heartbeats,
    }


def _fc_state_dir() -> Path:
    from pathlib import Path as P
    return P(
        os.environ.get("TBE_FC_STATE_DIR")
        or os.path.join(os.environ.get("OUTPUT_DIR") or "/tmp", "fc_vms")
    )


def list_managed_firecracker_vms() -> List[Dict[str, Any]]:
    """List Firecracker VMs from state metas written by FirecrackerSandboxBackend."""
    import json
    from pathlib import Path as P
    rows: List[Dict[str, Any]] = []
    root = _fc_state_dir()
    if not root.is_dir():
        return rows
    for meta_p in root.glob("fc-*.json"):
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except Exception:
            continue
        vm_id = str(meta.get("vm_id") or meta_p.stem)
        pid = int(meta.get("pid") or 0)
        running = False
        if pid:
            try:
                os.kill(pid, 0)
                running = True
            except ProcessLookupError:
                running = False
            except PermissionError:
                running = True
            except OSError:
                running = False
        rows.append(
            {
                "id": vm_id,
                "pid": pid,
                "status": "running" if running else "exited",
                "user_id": meta.get("user_id"),
                "started_log": meta.get("log"),
                "meta_path": str(meta_p),
                "backend": "firecracker",
            }
        )
    return rows


def reap_exited_firecracker(*, remove: bool = True) -> int:
    n = 0
    from lumen.engine.services.sandbox_runtime.firecracker_backend import (
        FirecrackerSandboxBackend,
    )
    backend = FirecrackerSandboxBackend()
    for vm in list_managed_firecracker_vms():
        if str(vm.get("status") or "").lower() in {"running", "up"}:
            continue
        vid = str(vm.get("id") or "")
        if not vid:
            continue
        if remove:
            try:
                backend.stop(vid)
            except Exception:
                logger.warning("fc reap stop failed id=%s", vid[:24])
        n += 1
    return n


def enforce_max_lifetime_firecracker() -> int:
    max_sec = int((os.environ.get("TBE_BOT_MAX_LIFETIME_SEC") or "0").strip() or "0")
    if max_sec <= 0:
        return 0
    import time
    from pathlib import Path as P
    from lumen.engine.services.sandbox_runtime.firecracker_backend import (
        FirecrackerSandboxBackend,
    )
    backend = FirecrackerSandboxBackend()
    killed = 0
    root = _fc_state_dir()
    now = time.time()
    for vm in list_managed_firecracker_vms():
        if str(vm.get("status") or "").lower() != "running":
            continue
        log = vm.get("started_log") or ""
        started = None
        try:
            if log and P(log).is_file():
                started = P(log).stat().st_mtime
        except OSError:
            started = None
        meta_p = vm.get("meta_path") or ""
        if started is None and meta_p:
            try:
                started = P(meta_p).stat().st_mtime
            except OSError:
                continue
        if started is None:
            continue
        if now - float(started) < max_sec:
            continue
        vid = str(vm.get("id") or "")
        try:
            backend.stop(vid)
            killed += 1
            logger.warning("supervisor killed over-lifetime fc vm %s", vid[:24])
        except Exception:
            continue
    return killed
