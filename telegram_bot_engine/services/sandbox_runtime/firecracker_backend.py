"""Firecracker microVM backend — honest fail-closed implementation.

Will NOT report status=running unless:
  - KVM + firecracker + kernel + rootfs exist
  - TAP network is configured (TBE_FC_TAP) OR TBE_FC_ALLOW_NO_NET=1 (dev only)
  - Token delivery path exists (TBE_FC_TOKEN_DRIVE or TBE_FC_TOKEN_IN_BOOTARGS=1)

Claim is VM process started — not Telegram bot health.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import List

from .backend import SandboxBackend
from .types import SandboxHandle, SandboxProbe, SandboxSpec

logger = logging.getLogger(__name__)


def _bin() -> str:
    return (os.environ.get("TBE_FIRECRACKER_BIN") or shutil.which("firecracker") or "").strip()


def _kernel() -> str:
    return (os.environ.get("TBE_FC_KERNEL") or "").strip()


def _rootfs() -> str:
    return (os.environ.get("TBE_FC_ROOTFS") or "").strip()


def _kvm_ok() -> bool:
    return os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)


def _flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


class FirecrackerSandboxBackend(SandboxBackend):
    name = "firecracker"
    strength = 100

    def __init__(self) -> None:
        self._state_dir = Path(
            os.environ.get("TBE_FC_STATE_DIR")
            or os.path.join(os.environ.get("OUTPUT_DIR") or "/tmp", "fc_vms")
        )
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def probe(self) -> SandboxProbe:
        if not _kvm_ok():
            return SandboxProbe(self.name, False, "kvm_unavailable", self.strength)
        b = _bin()
        if not b or not os.path.isfile(b):
            return SandboxProbe(self.name, False, "firecracker_binary_missing", self.strength)
        if not _kernel() or not os.path.isfile(_kernel()):
            return SandboxProbe(self.name, False, "TBE_FC_KERNEL missing", self.strength)
        if not _rootfs() or not os.path.isfile(_rootfs()):
            return SandboxProbe(self.name, False, "TBE_FC_ROOTFS missing", self.strength)
        tap = (os.environ.get("TBE_FC_TAP") or "").strip()
        if not tap and not _flag("TBE_FC_ALLOW_NO_NET", "0"):
            return SandboxProbe(
                self.name,
                False,
                "TBE_FC_TAP required (or TBE_FC_ALLOW_NO_NET=1 for offline dev)",
                self.strength,
            )
        if not shutil.which("curl"):
            return SandboxProbe(self.name, False, "curl_required_for_firecracker_api", self.strength)
        return SandboxProbe(self.name, True, "firecracker_prereqs_ok", self.strength)

    def _api_socket(self, vm_id: str) -> Path:
        return self._state_dir / f"{vm_id}.sock"

    def _meta_path(self, vm_id: str) -> Path:
        return self._state_dir / f"{vm_id}.json"

    def start(self, spec: SandboxSpec) -> SandboxHandle:
        probe = self.probe()
        if not probe.available:
            return SandboxHandle(
                backend=self.name,
                deployment_id="",
                status="failed",
                message=f"firecracker_unavailable:{probe.reason}",
            )

        token_drive = (os.environ.get("TBE_FC_TOKEN_DRIVE") or "").strip()
        inject_boot = _flag("TBE_FC_TOKEN_IN_BOOTARGS", "0")
        if not token_drive and not inject_boot:
            return SandboxHandle(
                backend=self.name,
                deployment_id="",
                status="failed",
                message=(
                    "firecracker_token_path_missing: set TBE_FC_TOKEN_DRIVE or "
                    "TBE_FC_TOKEN_IN_BOOTARGS=1 (guest must read token)"
                ),
            )

        vm_id = f"fc-{spec.user_id}-{uuid.uuid4().hex[:10]}"
        sock = self._api_socket(vm_id)
        if sock.exists():
            try:
                sock.unlink()
            except OSError:
                pass

        rootfs_src = Path(_rootfs())
        rootfs_dst = self._state_dir / f"{vm_id}.ext4"
        try:
            shutil.copy2(rootfs_src, rootfs_dst)
        except Exception as exc:
            return SandboxHandle(
                self.name, "", status="failed",
                message=f"rootfs_copy_failed:{type(exc).__name__}",
            )

        log_path = self._state_dir / f"{vm_id}.log"
        boot_args = "console=ttyS0 reboot=k panic=1 pci=off"
        if inject_boot:
            boot_args += f" BOT_TOKEN={spec.bot_token}"

        cfg: dict = {
            "boot-source": {
                "kernel_image_path": _kernel(),
                "boot_args": boot_args,
            },
            "drives": [
                {
                    "drive_id": "rootfs",
                    "path_on_host": str(rootfs_dst),
                    "is_root_device": True,
                    "is_read_only": False,
                }
            ],
            "machine-config": {
                "vcpu_count": int(os.environ.get("TBE_FC_VCPUS") or "1"),
                "mem_size_mib": int(os.environ.get("TBE_FC_MEM_MIB") or "256"),
                "smt": False,
            },
        }

        tap = (os.environ.get("TBE_FC_TAP") or "").strip()
        if tap:
            cfg["network-interfaces"] = [
                {
                    "iface_id": "eth0",
                    "host_dev_name": tap,
                    "guest_mac": "AA:FC:00:00:00:01",
                }
            ]

        if token_drive:
            td_src = Path(token_drive)
            td_dst = self._state_dir / f"{vm_id}.token.img"
            try:
                if td_src.is_file():
                    shutil.copy2(td_src, td_dst)
                else:
                    return SandboxHandle(
                        self.name, "", status="failed",
                        message="TBE_FC_TOKEN_DRIVE not a file",
                    )
            except Exception as exc:
                return SandboxHandle(
                    self.name, "", status="failed",
                    message=f"token_drive_copy_failed:{type(exc).__name__}",
                )
            cfg["drives"].append(
                {
                    "drive_id": "token",
                    "path_on_host": str(td_dst),
                    "is_root_device": False,
                    "is_read_only": True,
                }
            )

        try:
            proc = subprocess.Popen(
                [_bin(), "--api-sock", str(sock)],
                stdout=open(log_path, "a"),
                stderr=subprocess.STDOUT,
                pass_fds=(),
            )
        except Exception as exc:
            return SandboxHandle(
                self.name, "", status="failed",
                message=f"firecracker_spawn_failed:{type(exc).__name__}",
            )

        for _ in range(50):
            if sock.exists():
                break
            time.sleep(0.1)
        if not sock.exists():
            proc.kill()
            return SandboxHandle(self.name, "", status="failed", message="api_sock_timeout")

        def _put(path: str, body: dict) -> None:
            data = json.dumps(body)
            r = subprocess.run(
                [
                    "curl", "--unix-socket", str(sock),
                    "-sS", "-X", "PUT",
                    f"http://localhost{path}",
                    "-H", "Content-Type: application/json",
                    "-d", data,
                ],
                capture_output=True,
                timeout=15,
                check=False,
            )
            if r.returncode != 0:
                raise RuntimeError(f"fc_api_put_failed:{path}:{(r.stderr or b'')!r}")

        try:
            _put("/boot-source", cfg["boot-source"])
            _put("/drives/rootfs", cfg["drives"][0])
            if len(cfg["drives"]) > 1:
                _put("/drives/token", cfg["drives"][1])
            _put("/machine-config", cfg["machine-config"])
            if "network-interfaces" in cfg:
                _put("/network-interfaces/eth0", cfg["network-interfaces"][0])
            _put("/actions", {"action_type": "InstanceStart"})
        except Exception as exc:
            proc.kill()
            return SandboxHandle(
                self.name, "", status="failed",
                message=f"firecracker_config_failed:{type(exc).__name__}:{exc}",
            )

        meta = {
            "pid": proc.pid,
            "vm_id": vm_id,
            "rootfs": str(rootfs_dst),
            "log": str(log_path),
            "user_id": spec.user_id,
            "project_path": spec.project_path,
            "token_fp": hashlib.sha256(spec.bot_token.encode()).hexdigest()[:16],
            "network": bool(tap),
            "claim": "vm_process_started_not_bot_health",
        }
        self._meta_path(vm_id).write_text(json.dumps(meta), encoding="utf-8")
        return SandboxHandle(
            backend=self.name,
            deployment_id=vm_id,
            container_or_vm_id=vm_id,
            status="running",
            message=f"firecracker_vm_process_started pid={proc.pid} (bot health not verified)",
            meta=meta,
        )

    def stop(self, handle_or_id: str) -> SandboxHandle:
        meta_p = self._meta_path(handle_or_id)
        if meta_p.exists():
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                pid = int(meta.get("pid") or 0)
                if pid:
                    try:
                        os.kill(pid, 15)
                        time.sleep(0.5)
                    except ProcessLookupError:
                        pass
                    try:
                        os.kill(pid, 9)
                    except ProcessLookupError:
                        pass
            except Exception as exc:
                logger.warning("fc stop: %s", type(exc).__name__)
            try:
                meta_p.unlink()
            except OSError:
                pass
        sock = self._api_socket(handle_or_id)
        if sock.exists():
            try:
                sock.unlink()
            except OSError:
                pass
        return SandboxHandle(
            backend=self.name,
            deployment_id=handle_or_id,
            status="stopped",
            message="firecracker_stopped",
        )

    def status(self, handle_or_id: str) -> SandboxHandle:
        meta_p = self._meta_path(handle_or_id)
        if not meta_p.exists():
            return SandboxHandle(self.name, handle_or_id, status="stopped", message="no_meta")
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            pid = int(meta.get("pid") or 0)
            running = False
            if pid:
                try:
                    os.kill(pid, 0)
                    running = True
                except ProcessLookupError:
                    running = False
            return SandboxHandle(
                self.name, handle_or_id,
                container_or_vm_id=handle_or_id,
                status="running" if running else "stopped",
                message="vm_process" if running else "stopped",
                meta=meta,
            )
        except Exception as exc:
            return SandboxHandle(self.name, handle_or_id, status="unknown", message=str(exc)[:120])

    def logs(self, handle_or_id: str, *, limit: int = 50) -> List[str]:
        meta_p = self._meta_path(handle_or_id)
        if not meta_p.exists():
            return []
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            log = Path(meta.get("log") or "")
            if not log.is_file():
                return []
            return log.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
        except Exception:
            return []
