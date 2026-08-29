"""Sandbox supervisor — non-blocking docker I/O by design.

Architecture:
  - Background worker (hosting/worker.py) may use the sync helpers.
  - Async request handlers MUST use ``*_async`` helpers (create_subprocess_exec
    or asyncio.to_thread). Never call ``_docker`` / ``list_managed_containers``
    on the aiohttp event loop.

Listing uses a single ``docker ps`` with labels — never N sequential inspects.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _docker(args: List[str], timeout: float = 30.0) -> tuple[int, str]:
    """Synchronous docker CLI — **worker/thread context only**.

    Hard guard: if a running asyncio loop exists in this thread, refuse.
    Callers on the API event loop must use ``list_managed_containers_async``.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # no running loop — OK for worker threads
    else:
        raise RuntimeError(
            "blocking _docker() called from async event loop — "
            "use list_managed_containers_async / _docker_async"
        )
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


async def _docker_async(args: List[str], timeout: float = 30.0) -> tuple[int, str]:
    """Non-blocking docker CLI (fallback only). Prefer aiodocker HTTP API."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return 124, "timeout"
        out = (stdout or b"").decode("utf-8", errors="replace")
        return int(proc.returncode or 0), out
    except FileNotFoundError:
        return 127, "docker_not_found"
    except Exception as exc:
        return 1, f"{type(exc).__name__}:{exc}"


async def _list_via_aiodocker() -> List[Dict[str, Any]] | None:
    """Docker Engine API over unix socket — zero subprocess, zero event-loop block.

    2026 standard (Home Assistant Supervisor, aio-libs/aiodocker): talk HTTP to
    the daemon, not ``docker`` CLI forks.
    """
    try:
        import aiodocker
    except ImportError:
        return None
    docker = None
    try:
        docker = aiodocker.Docker()
        # filters: label=tbe.managed=1
        raw = await asyncio.wait_for(
            docker.containers.list(all=True, filters={"label": ["tbe.managed=1"]}),
            timeout=20.0,
        )
        rows: List[Dict[str, Any]] = []
        for c in raw or []:
            # aiodocker may return dict or DockerContainer
            data = c if isinstance(c, dict) else getattr(c, "_container", None) or {}
            if not data and hasattr(c, "show"):
                try:
                    data = await c.show()
                except Exception:
                    data = {}
            cid = str(data.get("Id") or data.get("ID") or "")[:64]
            if not cid:
                continue
            names = data.get("Names") or []
            name = ""
            if names:
                name = str(names[0]).lstrip("/")
            state = data.get("State") or ""
            if isinstance(state, dict):
                status = str(state.get("Status") or "")
            else:
                status = str(state or data.get("Status") or "")
            labels = data.get("Labels") or {}
            if not isinstance(labels, dict):
                labels = {}
            labels = {str(k): str(v) for k, v in labels.items()}
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
    except Exception as exc:
        logger.debug("aiodocker list failed: %s", type(exc).__name__)
        return None
    finally:
        if docker is not None:
            try:
                await docker.close()
            except Exception:
                pass


def _parse_ps_rows(out: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        cid = (parts[0] if parts else "").strip()
        if not cid:
            continue
        name = parts[1] if len(parts) > 1 else ""
        status = parts[2] if len(parts) > 2 else ""
        labels: Dict[str, str] = {}
        if len(parts) > 3 and parts[3]:
            labels["tbe.tenant_id"] = parts[3]
        if len(parts) > 4 and parts[4]:
            labels["tbe.bot_id"] = parts[4]
        if len(parts) > 5 and parts[5]:
            labels["tbe.user"] = parts[5]
        if len(parts) > 6 and parts[6]:
            labels["tbe.managed"] = parts[6]
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


_PS_FORMAT = (
    '{{.ID}}\t{{.Names}}\t{{.Status}}\t'
    '{{.Label "tbe.tenant_id"}}\t{{.Label "tbe.bot_id"}}\t{{.Label "tbe.user"}}\t'
    '{{.Label "tbe.managed"}}'
)
_PS_ARGS = [
    "ps", "-a",
    "--filter", "label=tbe.managed=1",
    "--format", _PS_FORMAT,
]


def list_managed_containers() -> List[Dict[str, Any]]:
    """Sync list — single docker ps (worker/thread only). Guarded against event-loop use."""
    code, out = _docker(list(_PS_ARGS), timeout=20.0)
    if code != 0:
        return []
    return _parse_ps_rows(out)


async def list_managed_containers_async() -> List[Dict[str, Any]]:
    """Async list — aiodocker HTTP API first, CLI subprocess only as fallback."""
    via_api = await _list_via_aiodocker()
    if via_api is not None:
        return via_api
    code, out = await _docker_async(list(_PS_ARGS), timeout=20.0)
    if code != 0:
        return []
    return _parse_ps_rows(out)


def reap_exited(*, remove: bool = True) -> int:
    n = 0
    for c in list_managed_containers():
        st = (c.get("status") or "").lower()
        if st.startswith("exited") or st.startswith("dead") or st == "exited":
            if remove:
                _docker(["rm", "-f", str(c.get("id") or "")], timeout=15.0)
            n += 1
    return n


def enforce_max_lifetime() -> int:
    """Kill managed containers older than TBE_BOT_MAX_LIFETIME_SEC — one multi-ID inspect."""
    max_sec = int((os.environ.get("TBE_BOT_MAX_LIFETIME_SEC") or "0").strip() or "0")
    if max_sec <= 0:
        return 0
    containers = list_managed_containers()
    ids = [str(c.get("id") or "") for c in containers if c.get("id")]
    if not ids:
        return 0
    c2, insp = _docker(["inspect", "--format", "{{.Id}} {{.State.StartedAt}}", *ids], timeout=30.0)
    if c2 != 0 or not (insp or "").strip():
        return 0
    killed = 0
    now = time.time()
    for line in insp.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        cid, started = parts[0][:64], parts[1].strip()
        try:
            ts = started.replace("Z", "+00:00")
            if "." in ts:
                head, rest = ts.split(".", 1)
                frac = "".join(ch for ch in rest if ch.isdigit())[:6]
                tz = rest[len("".join(ch for ch in rest if ch.isdigit())):]
                ts = f"{head}.{frac}{tz}" if frac else f"{head}{tz}"
            started_ts = datetime.fromisoformat(ts).timestamp()
            if now - started_ts > max_sec:
                _docker(["rm", "-f", cid], timeout=15.0)
                killed += 1
                logger.warning("supervisor killed over-lifetime container %s", cid[:12])
        except Exception:
            continue
    return killed


def supervisor_tick() -> Dict[str, int]:
    """Sync tick for background worker thread only — not for aiohttp handlers."""
    containers = list_managed_containers()  # single docker ps
    reaped = 0
    for c in containers:
        st = (c.get("status") or "").lower()
        if st.startswith("exited") or st.startswith("dead") or st == "exited":
            _docker(["rm", "-f", str(c.get("id") or "")], timeout=15.0)
            reaped += 1
    lifetime_killed = enforce_max_lifetime()
    fc_reaped = reap_exited_firecracker(remove=True)
    fc_lifetime = enforce_max_lifetime_firecracker()
    heartbeats = 0
    try:
        from lumen.engine.services.usage.heartbeat import emit_host_heartbeat
        for c in containers:
            st = (c.get("status") or "").lower()
            if st and st not in {"running", "up"} and not st.startswith("up"):
                continue
            labels = c.get("labels") if isinstance(c.get("labels"), dict) else {}
            tenant_id = str(labels.get("tbe.tenant_id") or c.get("tenant_id") or "").strip()
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


async def supervisor_tick_async() -> Dict[str, int]:
    """Async tick for any request-path caller — all docker I/O is non-blocking."""
    return await asyncio.to_thread(supervisor_tick)


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
