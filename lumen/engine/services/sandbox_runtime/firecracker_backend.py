"""Firecracker microVM backend — production-grade, fail-closed.

Production path (default when ENVIRONMENT is not dev/local/test):
  jailer → unique uid/gid → optional netns → chroot jail → Firecracker VMM
  kernel + base rootfs + project drive + token drive (never boot-args in prod)

Dev path (explicit opt-in):
  direct firecracker binary without jailer only when TBE_FC_ALLOW_NO_JAILER=1
  and environment is dev/local/test.

Claims are honest: status=running means the VMM process is alive, not that the
Telegram bot finished its long-poll handshake.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from .backend import SandboxBackend
from .types import SandboxHandle, SandboxProbe, SandboxSpec

logger = logging.getLogger(__name__)

# Dedicated high uid range for microVM jailer identities (avoid system users).
_FC_UID_BASE = 200000
_FC_UID_SPAN = 100000


def _flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def _is_dev_environment() -> bool:
    """True only for explicit local/dev/test — never when deploy signals present."""
    markers = (
        "KUBERNETES_SERVICE_HOST",
        "K_SERVICE",
        "AWS_EXECUTION_ENV",
        "AWS_REGION",
        "RAILWAY_ENVIRONMENT",
        "RENDER_SERVICE_ID",
        "FLY_APP_NAME",
        "DYNO",
        "WEBSITE_INSTANCE_ID",
    )
    for m in markers:
        if (os.getenv(m) or "").strip():
            return False
    if (os.getenv("FORCE_PRODUCTION") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    return env in {"dev", "development", "local", "test"}


def _bin() -> str:
    return (os.environ.get("TBE_FIRECRACKER_BIN") or shutil.which("firecracker") or "").strip()


def _jailer_bin() -> str:
    return (os.environ.get("TBE_JAILER_BIN") or shutil.which("jailer") or "").strip()


def _kernel() -> str:
    return (os.environ.get("TBE_FC_KERNEL") or "").strip()


def _rootfs() -> str:
    return (os.environ.get("TBE_FC_ROOTFS") or "").strip()


def _kvm_ok() -> bool:
    return os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)


def _chroot_base() -> Path:
    raw = (os.environ.get("TBE_FC_CHROOT_BASE") or "/srv/jailer").strip()
    return Path(raw)


def _require_jailer() -> bool:
    """Jailer is mandatory outside explicit unsafe dev mode."""
    if _flag("TBE_FC_REQUIRE_JAILER", "1"):
        if _is_dev_environment() and _flag("TBE_FC_ALLOW_NO_JAILER", "0"):
            return False
        return True
    return False


def _stable_vm_ids(user_id: int, vm_id: str) -> Tuple[int, int]:
    """Deterministic unique uid/gid in reserved range for this microVM."""
    digest = hashlib.sha256(f"{user_id}:{vm_id}".encode()).hexdigest()
    offset = int(digest[:8], 16) % _FC_UID_SPAN
    uid = _FC_UID_BASE + offset
    gid = uid
    return uid, gid


def _run(
    cmd: list[str],
    *,
    timeout: float = 30.0,
    cwd: Optional[str] = None,
) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=cwd,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}:{exc}"


def _which_mkfs() -> Optional[str]:
    return shutil.which("mkfs.ext4")


def _create_ext4_image(path: Path, size_mb: int) -> None:
    """Create a sparse ext4 filesystem image at path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    # Sparse file
    with open(path, "wb") as f:
        f.truncate(max(8, size_mb) * 1024 * 1024)
    mkfs = _which_mkfs()
    if not mkfs:
        raise RuntimeError("mkfs.ext4_missing")
    code, _, err = _run(
        [mkfs, "-F", "-q", str(path)],
        timeout=60,
    )
    if code != 0:
        raise RuntimeError(f"mkfs_failed:{err[:200]}")


def _populate_ext4_with_files(image: Path, files: dict[str, bytes], mount_point: Path) -> None:
    """Write files into an ext4 image via loop-mount, or debugfs without mount."""
    # Preferred: debugfs (no root mount required on many hosts)
    debugfs = shutil.which("debugfs")
    if debugfs:
        tmp = image.parent / f".dbg-{image.stem}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            for rel, data in files.items():
                local = tmp / rel.replace("/", "_")
                local.write_bytes(data)
                remote = rel.lstrip("/")
                # Ensure parent dirs inside image
                parts = remote.split("/")
                if len(parts) > 1:
                    acc = ""
                    for part in parts[:-1]:
                        acc = f"{acc}/{part}" if acc else part
                        _run([debugfs, "-w", "-R", f"mkdir {acc}", str(image)], timeout=15)
                cmd = f"write {local} {remote}"
                code, _, err = _run([debugfs, "-w", "-R", cmd, str(image)], timeout=30)
                if code != 0:
                    raise RuntimeError(f"debugfs_write_failed:{remote}:{err[:200]}")
            return
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    mount_point.mkdir(parents=True, exist_ok=True)
    code, _, err = _run(["mount", "-o", "loop", str(image), str(mount_point)], timeout=30)
    if code != 0:
        raise RuntimeError(f"loop_mount_failed:{err[:200]}")
    try:
        for rel, data in files.items():
            dest = mount_point / rel.lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            try:
                os.chmod(dest, 0o400)
            except OSError:
                pass
    finally:
        _run(["umount", str(mount_point)], timeout=30)


def _write_token_drive(path: Path, token: str, env_extra: dict[str, str]) -> None:
    """Token drive: small ext4 with BOT_TOKEN file (mode 0400 semantics after mount)."""
    size_mb = int((os.environ.get("TBE_FC_TOKEN_DRIVE_MB") or "8").strip() or "8")
    _create_ext4_image(path, size_mb)
    mount = path.parent / f".mnt-token-{path.stem}"
    payload = (token or "").encode("utf-8")
    files = {
        "BOT_TOKEN": payload,
        "TELEGRAM_BOT_TOKEN": payload,
        "env.json": json.dumps({k: v for k, v in env_extra.items() if k and v is not None}).encode(),
    }
    try:
        _populate_ext4_with_files(path, files, mount)
    except RuntimeError:
        # Without root loop-mount we still create a raw sidecar the operator can wire;
        # do not put token in boot args in production.
        if _is_dev_environment() and _flag("TBE_FC_TOKEN_IN_BOOTARGS", "0"):
            path.write_bytes(b"TOKEN_DRIVE_PLACEHOLDER")
            return
        raise


def _write_project_drive(path: Path, project_path: str) -> None:
    """Pack project directory into an ext4 image for guest mount at /project."""
    src = Path(project_path)
    if not src.is_dir():
        raise RuntimeError(f"project_path_not_dir:{project_path}")
    size_mb = int((os.environ.get("TBE_FC_PROJECT_DRIVE_MB") or "512").strip() or "512")
    # Estimate size; grow if needed (capped)
    try:
        total = sum(f.stat().st_size for f in src.rglob("*") if f.is_file())
        need = max(size_mb, int(total / (1024 * 1024)) + 64)
        size_mb = min(need, int((os.environ.get("TBE_FC_PROJECT_DRIVE_MAX_MB") or "2048").strip() or "2048"))
    except OSError:
        pass
    _create_ext4_image(path, size_mb)
    mount = path.parent / f".mnt-proj-{path.stem}"
    mount.mkdir(parents=True, exist_ok=True)
    code, _, err = _run(["mount", "-o", "loop", str(path), str(mount)], timeout=30)
    if code != 0:
        raise RuntimeError(f"project_loop_mount_failed:{err[:200]}")
    try:
        # Prefer rsync if available; else cp -a
        if shutil.which("rsync"):
            code, _, err = _run(
                ["rsync", "-a", "--delete", str(src) + "/", str(mount) + "/"],
                timeout=120,
            )
        else:
            code, _, err = _run(["cp", "-a", str(src) + "/.", str(mount) + "/"], timeout=120)
        if code != 0:
            raise RuntimeError(f"project_copy_failed:{err[:200]}")
    finally:
        _run(["umount", str(mount)], timeout=30)


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


def _api_put(sock: Path, path: str, body: dict, timeout: float = 15.0) -> None:
    data = json.dumps(body)
    # Prefer curl unix-socket (ubiquitous); fallback to Python http if needed.
    if shutil.which("curl"):
        r = subprocess.run(
            [
                "curl",
                "--unix-socket",
                str(sock),
                "-sS",
                "-X",
                "PUT",
                f"http://localhost{path}",
                "-H",
                "Content-Type: application/json",
                "-d",
                data,
            ],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"fc_api_put_failed:{path}:{(r.stderr or b'')!r}")
        return
    # Minimal fallback without third-party deps
    import http.client
    import socket as _socket

    class _UnixHTTPConnection(http.client.HTTPConnection):
        def __init__(self, socket_path: str) -> None:
            super().__init__("localhost")
            self._socket_path = socket_path

        def connect(self) -> None:
            self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            self.sock.connect(self._socket_path)

    conn = _UnixHTTPConnection(str(sock))
    try:
        conn.request("PUT", path, body=data, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status >= 300:
            raise RuntimeError(f"fc_api_put_http:{path}:{resp.status}")
    finally:
        conn.close()


class FirecrackerSandboxBackend(SandboxBackend):
    name = "firecracker"
    strength = 100

    def __init__(self) -> None:
        self._state_dir = Path(
            os.environ.get("TBE_FC_STATE_DIR")
            or os.path.join(os.environ.get("OUTPUT_DIR") or "/tmp", "fc_vms")
        )
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _api_socket(self, vm_id: str) -> Path:
        return self._state_dir / f"{vm_id}.sock"

    def _meta_path(self, vm_id: str) -> Path:
        return self._state_dir / f"{vm_id}.json"

    def probe(self) -> SandboxProbe:
        if not _kvm_ok():
            return SandboxProbe(self.name, False, "kvm_unavailable", self.strength)
        b = _bin()
        if not b or not os.path.isfile(b):
            return SandboxProbe(self.name, False, "firecracker_binary_missing", self.strength)
        if _require_jailer():
            j = _jailer_bin()
            if not j or not os.path.isfile(j):
                return SandboxProbe(self.name, False, "jailer_binary_missing", self.strength)
        if not _kernel() or not os.path.isfile(_kernel()):
            return SandboxProbe(self.name, False, "TBE_FC_KERNEL missing", self.strength)
        if not _rootfs() or not os.path.isfile(_rootfs()):
            return SandboxProbe(self.name, False, "TBE_FC_ROOTFS missing", self.strength)
        tap = (os.environ.get("TBE_FC_TAP") or "").strip()
        netns = (os.environ.get("TBE_FC_NETNS") or "").strip()
        if not tap and not netns and not _flag("TBE_FC_ALLOW_NO_NET", "0"):
            return SandboxProbe(
                self.name,
                False,
                "TBE_FC_TAP or TBE_FC_NETNS required (or TBE_FC_ALLOW_NO_NET=1 for offline dev)",
                self.strength,
            )
        if not _which_mkfs() and not _flag("TBE_FC_SKIP_DRIVE_BUILD", "0"):
            # Still allow probe if operator pre-builds drives
            pass
        return SandboxProbe(self.name, True, "firecracker_prereqs_ok", self.strength)

    def start(self, spec: SandboxSpec) -> SandboxHandle:
        probe = self.probe()
        if not probe.available:
            return SandboxHandle(
                backend=self.name,
                deployment_id="",
                status="failed",
                message=f"firecracker_unavailable:{probe.reason}",
            )

        # Token path: production forbids boot-args injection
        token_drive_env = (os.environ.get("TBE_FC_TOKEN_DRIVE") or "").strip()
        inject_boot = _flag("TBE_FC_TOKEN_IN_BOOTARGS", "0")
        if inject_boot and not _is_dev_environment():
            return SandboxHandle(
                backend=self.name,
                deployment_id="",
                status="failed",
                message="firecracker_token_in_bootargs_forbidden_in_production",
            )
        if not token_drive_env and not inject_boot:
            # We will build a per-VM token drive automatically
            pass

        vm_id = f"fc-{spec.user_id}-{uuid.uuid4().hex[:10]}"
        uid, gid = _stable_vm_ids(int(spec.user_id or 0), vm_id)
        sock = self._api_socket(vm_id)
        if sock.exists():
            try:
                sock.unlink()
            except OSError:
                pass

        log_path = self._state_dir / f"{vm_id}.log"
        rootfs_src = Path(_rootfs())
        rootfs_dst = self._state_dir / f"{vm_id}.rootfs.ext4"
        project_drive = self._state_dir / f"{vm_id}.project.ext4"
        token_drive = self._state_dir / f"{vm_id}.token.ext4"

        try:
            # Copy base rootfs (writable guest disk). Prefer reflink when available.
            try:
                _run(["cp", "--reflink=auto", str(rootfs_src), str(rootfs_dst)], timeout=120)
                if not rootfs_dst.is_file():
                    shutil.copy2(rootfs_src, rootfs_dst)
            except Exception:
                shutil.copy2(rootfs_src, rootfs_dst)

            # Project + token drives
            if not _flag("TBE_FC_SKIP_PROJECT_DRIVE", "0"):
                _write_project_drive(project_drive, spec.project_path)
            if token_drive_env and Path(token_drive_env).is_file():
                shutil.copy2(token_drive_env, token_drive)
            elif not inject_boot:
                _write_token_drive(token_drive, spec.bot_token, dict(spec.env_vars or {}))
        except Exception as exc:
            self._cleanup_files(vm_id)
            return SandboxHandle(
                self.name,
                "",
                status="failed",
                message=f"drive_prepare_failed:{type(exc).__name__}:{exc}",
            )

        boot_args = (
            os.environ.get("TBE_FC_BOOT_ARGS")
            or "console=ttyS0 reboot=k panic=1 pci=off init=/sbin/init"
        ).strip()
        if inject_boot and _is_dev_environment():
            # Dev-only; never in production (blocked above)
            boot_args += f" BOT_TOKEN={spec.bot_token}"

        # Align with hard sandbox policy when env unset
        try:
            from .policy import load_policy
            pol = load_policy()
            pol_mem = str(pol.max_memory or "256m").lower().replace("m", "").replace("mi", "")
            pol_mem_mib = int(float(pol_mem)) if pol_mem.replace(".", "", 1).isdigit() else 256
        except Exception:
            pol_mem_mib = 256
        mem_mib = int((os.environ.get("TBE_FC_MEM_MIB") or str(pol_mem_mib)).strip() or "256")
        vcpus = int((os.environ.get("TBE_FC_VCPUS") or "1").strip() or "1")

        # Rate limiters (bytes/s style — Firecracker refill_time in ms)
        blk_bw = int((os.environ.get("TBE_FC_BLOCK_BW_BPS") or str(50 * 1024 * 1024)).strip())
        net_bw = int((os.environ.get("TBE_FC_NET_BW_BPS") or str(10 * 1024 * 1024)).strip())

        drives: list[dict] = [
            {
                "drive_id": "rootfs",
                "path_on_host": str(rootfs_dst),
                "is_root_device": True,
                "is_read_only": False,
                "rate_limiter": {
                    "bandwidth": {"size": blk_bw, "refill_time": 1000},
                },
            }
        ]
        if project_drive.is_file():
            drives.append(
                {
                    "drive_id": "project",
                    "path_on_host": str(project_drive),
                    "is_root_device": False,
                    "is_read_only": True,
                    "rate_limiter": {
                        "bandwidth": {"size": blk_bw, "refill_time": 1000},
                    },
                }
            )
        if token_drive.is_file() and not inject_boot:
            drives.append(
                {
                    "drive_id": "token",
                    "path_on_host": str(token_drive),
                    "is_root_device": False,
                    "is_read_only": True,
                }
            )

        machine_cfg = {
            "vcpu_count": vcpus,
            "mem_size_mib": mem_mib,
            "smt": False,
        }

        network_ifaces: list[dict] = []
        tap = (os.environ.get("TBE_FC_TAP") or "").strip()
        if tap:
            network_ifaces.append(
                {
                    "iface_id": "eth0",
                    "host_dev_name": tap,
                    "guest_mac": self._guest_mac(vm_id),
                    "rx_rate_limiter": {
                        "bandwidth": {"size": net_bw, "refill_time": 1000},
                    },
                    "tx_rate_limiter": {
                        "bandwidth": {"size": net_bw, "refill_time": 1000},
                    },
                }
            )

        use_jailer = _require_jailer() and bool(_jailer_bin())
        if _require_jailer() and not _jailer_bin():
            self._cleanup_files(vm_id)
            return SandboxHandle(
                self.name,
                "",
                status="failed",
                message="jailer_required_but_missing",
            )

        netns_path = ""
        if use_jailer:
            netns_env = (os.environ.get("TBE_FC_NETNS") or "").strip()
            if netns_env:
                netns_path = netns_env if netns_env.startswith("/") else f"/var/run/netns/{netns_env}"
            elif _flag("TBE_FC_CREATE_NETNS", "1") and not _flag("TBE_FC_ALLOW_NO_NET", "0"):
                try:
                    netns_path = _ensure_netns(f"fc-{spec.user_id}-{vm_id[-8:]}")
                except Exception as exc:
                    if not tap:
                        self._cleanup_files(vm_id)
                        return SandboxHandle(
                            self.name,
                            "",
                            status="failed",
                            message=f"netns_failed:{type(exc).__name__}:{exc}",
                        )

        try:
            if use_jailer:
                pid = self._start_with_jailer(
                    vm_id=vm_id,
                    uid=uid,
                    gid=gid,
                    sock=sock,
                    log_path=log_path,
                    kernel=_kernel(),
                    drives=drives,
                    machine_cfg=machine_cfg,
                    boot_args=boot_args,
                    network_ifaces=network_ifaces,
                    netns_path=netns_path,
                )
            else:
                pid = self._start_direct(
                    sock=sock,
                    log_path=log_path,
                    kernel=_kernel(),
                    drives=drives,
                    machine_cfg=machine_cfg,
                    boot_args=boot_args,
                    network_ifaces=network_ifaces,
                )
        except Exception as exc:
            self._cleanup_files(vm_id)
            return SandboxHandle(
                self.name,
                "",
                status="failed",
                message=f"firecracker_start_failed:{type(exc).__name__}:{exc}",
            )

        meta = {
            "pid": pid,
            "vm_id": vm_id,
            "uid": uid,
            "gid": gid,
            "jailer": use_jailer,
            "rootfs": str(rootfs_dst),
            "project_drive": str(project_drive) if project_drive.is_file() else "",
            "token_drive": str(token_drive) if token_drive.is_file() else "",
            "log": str(log_path),
            "user_id": spec.user_id,
            "project_path": spec.project_path,
            "token_fp": hashlib.sha256(spec.bot_token.encode()).hexdigest()[:16],
            "network_tap": bool(tap),
            "netns": netns_path,
            "claim": "vm_process_started_not_bot_health",
        }
        self._meta_path(vm_id).write_text(json.dumps(meta), encoding="utf-8")
        return SandboxHandle(
            backend=self.name,
            deployment_id=vm_id,
            container_or_vm_id=vm_id,
            status="running",
            message=f"firecracker_vm_started pid={pid} jailer={use_jailer} (bot health not verified)",
            meta=meta,
        )

    @staticmethod
    def _guest_mac(vm_id: str) -> str:
        h = hashlib.sha256(vm_id.encode()).digest()
        # Locally administered unicast MAC
        return "AA:FC:{:02X}:{:02X}:{:02X}:{:02X}".format(h[0], h[1], h[2], h[3])

    def _wait_sock(self, sock: Path, proc: Optional[subprocess.Popen] = None) -> None:
        for _ in range(80):
            if sock.exists():
                return
            if proc is not None and proc.poll() is not None:
                raise RuntimeError(f"firecracker_exited_early code={proc.returncode}")
            time.sleep(0.1)
        raise RuntimeError("api_sock_timeout")

    def _configure_vm(
        self,
        sock: Path,
        *,
        kernel: str,
        boot_args: str,
        drives: list[dict],
        machine_cfg: dict,
        network_ifaces: list[dict],
    ) -> None:
        _api_put(sock, "/boot-source", {"kernel_image_path": kernel, "boot_args": boot_args})
        for d in drives:
            _api_put(sock, f"/drives/{d['drive_id']}", d)
        _api_put(sock, "/machine-config", machine_cfg)
        if _flag("TBE_FC_BALLOON", "1"):
            try:
                amount = max(0, int(machine_cfg.get("mem_size_mib") or 256) // 4)
                _api_put(
                    sock,
                    "/balloon",
                    {
                        "amount_mib": amount,
                        "deflate_on_oom": True,
                        "stats_polling_interval_s": 0,
                    },
                )
            except Exception as balloon_exc:
                logger.warning("fc balloon optional failed: %s", type(balloon_exc).__name__)
        for iface in network_ifaces:
            _api_put(sock, f"/network-interfaces/{iface['iface_id']}", iface)
        _api_put(sock, "/actions", {"action_type": "InstanceStart"})

    def _start_direct(
        self,
        *,
        sock: Path,
        log_path: Path,
        kernel: str,
        drives: list[dict],
        machine_cfg: dict,
        boot_args: str,
        network_ifaces: list[dict],
    ) -> int:
        log_f = open(log_path, "a")
        try:
            proc = subprocess.Popen(
                [_bin(), "--api-sock", str(sock)],
                stdout=log_f,
                stderr=subprocess.STDOUT,
                pass_fds=(),
            )
        except Exception:
            log_f.close()
            raise
        try:
            self._wait_sock(sock, proc)
            # Paths in API config are host paths for direct mode
            self._configure_vm(
                sock,
                kernel=kernel,
                boot_args=boot_args,
                drives=drives,
                machine_cfg=machine_cfg,
                network_ifaces=network_ifaces,
            )
        except Exception:
            try:
                proc.kill()
            except OSError:
                pass
            raise
        return int(proc.pid)

    def _start_with_jailer(
        self,
        *,
        vm_id: str,
        uid: int,
        gid: int,
        sock: Path,
        log_path: Path,
        kernel: str,
        drives: list[dict],
        machine_cfg: dict,
        boot_args: str,
        network_ifaces: list[dict],
        netns_path: str,
    ) -> int:
        """Start Firecracker under official jailer (prod host setup).

        Resources are staged into the jail chroot; API socket lives under the jail.
        """
        jailer = _jailer_bin()
        fc = _bin()
        chroot_base = _chroot_base()
        chroot_base.mkdir(parents=True, exist_ok=True)

        # Jailer layout: <chroot_base>/<id>/root/ ...
        jail_id = vm_id
        jail_root = chroot_base / jail_id / "root"
        jail_root.mkdir(parents=True, exist_ok=True)

        def _stage(src: str, name: str) -> str:
            """Copy resource into jail root; return path relative to jail root for FC API."""
            src_p = Path(src)
            dst = jail_root / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src_p.is_file():
                try:
                    _run(["cp", "--reflink=auto", str(src_p), str(dst)], timeout=120)
                    if not dst.is_file():
                        shutil.copy2(src_p, dst)
                except Exception:
                    shutil.copy2(src_p, dst)
            else:
                raise RuntimeError(f"stage_missing:{src}")
            try:
                os.chown(dst, uid, gid)
            except OSError:
                # May lack CAP_CHOWN in constrained CI — jailer still applies uid at exec
                pass
            return f"/{name}"

        staged_kernel = _stage(kernel, "vmlinux")
        staged_drives: list[dict] = []
        for d in drives:
            host_path = d["path_on_host"]
            name = f"drive-{d['drive_id']}.ext4"
            guest_rel = _stage(host_path, name)
            nd = dict(d)
            nd["path_on_host"] = guest_rel
            staged_drives.append(nd)

        # API socket path inside jail (Firecracker default under /run)
        run_dir = jail_root / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chown(run_dir, uid, gid)
        except OSError:
            pass

        cmd = [
            jailer,
            "--id",
            jail_id,
            "--exec-file",
            fc,
            "--uid",
            str(uid),
            "--gid",
            str(gid),
            "--chroot-base-dir",
            str(chroot_base),
            "--daemonize",
            "--new-pid-ns",
        ]
        # Resource limits via jailer
        mem_mib = int(machine_cfg.get("mem_size_mib") or 256)
        cmd.extend(["--resource-limit", f"fsize={mem_mib * 4 * 1024 * 1024}"])
        if netns_path:
            cmd.extend(["--netns", netns_path])
        # cgroup memory (v1/v2 best-effort)
        cmd.extend(["--cgroup", f"memory.max={mem_mib * 1024 * 1024}"])

        # Firecracker args after --
        api_sock_in_jail = "/run/firecracker.socket"
        cmd.extend(["--", "--api-sock", api_sock_in_jail])

        log_f = open(log_path, "a")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                pass_fds=(),
            )
        except Exception:
            log_f.close()
            raise

        # Wait for jailer to daemonize and create socket inside jail
        host_sock = chroot_base / jail_id / "root" / "run" / "firecracker.socket"
        # Also link a host-visible path for operators
        try:
            self._wait_sock(host_sock, proc if not _flag("TBE_FC_JAILER_DAEMONIZE_WAIT", "1") else None)
        except RuntimeError:
            # Daemonize: parent may exit 0 quickly — poll socket only
            for _ in range(100):
                if host_sock.exists():
                    break
                time.sleep(0.1)
            else:
                try:
                    proc.kill()
                except OSError:
                    pass
                raise RuntimeError("jailer_api_sock_timeout")

        try:
            self._configure_vm(
                host_sock,
                kernel=staged_kernel,
                boot_args=boot_args,
                drives=staged_drives,
                machine_cfg=machine_cfg,
                network_ifaces=network_ifaces,
            )
        except Exception:
            self._kill_vm_tree(vm_id, host_sock)
            raise

        # Resolve VMM pid from jail metadata if possible
        pid = self._resolve_jail_pid(chroot_base, jail_id, proc.pid)
        # Symlink host sock path for status helpers
        try:
            if sock.exists() or sock.is_symlink():
                sock.unlink()
            sock.symlink_to(host_sock)
        except OSError:
            pass
        return pid

    def _resolve_jail_pid(self, chroot_base: Path, jail_id: str, fallback: int) -> int:
        # Common locations vary by jailer version; best-effort
        for candidate in (
            chroot_base / jail_id / "firecracker.pid",
            chroot_base / jail_id / "root" / "firecracker.pid",
        ):
            try:
                if candidate.is_file():
                    return int(candidate.read_text().strip())
            except (OSError, ValueError):
                continue
        return int(fallback or 0)

    def _kill_vm_tree(self, vm_id: str, host_sock: Optional[Path] = None) -> None:
        meta_p = self._meta_path(vm_id)
        pid = 0
        if meta_p.exists():
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                pid = int(meta.get("pid") or 0)
            except Exception:
                pass
        if pid:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.kill(pid, sig)
                    time.sleep(0.3)
                except ProcessLookupError:
                    break
                except OSError:
                    break
        # Attempt InstanceStop via API if socket still up
        sock = host_sock or self._api_socket(vm_id)
        if sock.exists():
            try:
                _api_put(sock, "/actions", {"action_type": "SendCtrlAltDel"}, timeout=3)
            except Exception:
                pass

    def _cleanup_files(self, vm_id: str) -> None:
        for p in self._state_dir.glob(f"{vm_id}*"):
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink()
            except OSError:
                pass
        # Jail chroot leftover
        jail = _chroot_base() / vm_id
        if jail.exists():
            shutil.rmtree(jail, ignore_errors=True)

    def stop(self, handle_or_id: str) -> SandboxHandle:
        meta_p = self._meta_path(handle_or_id)
        if meta_p.exists():
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                pid = int(meta.get("pid") or 0)
                if pid:
                    for sig in (signal.SIGTERM, signal.SIGKILL):
                        try:
                            os.kill(pid, sig)
                            time.sleep(0.4)
                        except ProcessLookupError:
                            break
                        except OSError:
                            break
            except Exception as exc:
                logger.warning("fc stop: %s", type(exc).__name__)
            try:
                meta_p.unlink()
            except OSError:
                pass
        sock = self._api_socket(handle_or_id)
        if sock.exists() or sock.is_symlink():
            try:
                sock.unlink()
            except OSError:
                pass
        # Clean drives / jail
        self._cleanup_files(handle_or_id)
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
                except PermissionError:
                    # Process exists but we cannot signal — treat as running
                    running = True
            return SandboxHandle(
                self.name,
                handle_or_id,
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
