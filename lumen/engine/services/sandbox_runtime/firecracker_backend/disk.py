"""Disk image helpers: ext4 root project/token drives, guest agent inject."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .env import _flag
from .process_util import _run

logger = logging.getLogger(__name__)

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


def _inject_guest_agent(project_src: Path) -> None:
    """Copy supervisor into project tree so rootfs can exec it from /project."""
    try:
        from lumen.engine.services.sandbox_runtime.guest_agent import (
            BOOT_SH_PATH,
            SUPERVISOR_PATH,
        )
    except Exception:
        return
    dest = project_src / ".lumen_guest"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        if SUPERVISOR_PATH.is_file():
            shutil.copy2(SUPERVISOR_PATH, dest / "supervisor.py")
        if BOOT_SH_PATH.is_file():
            shutil.copy2(BOOT_SH_PATH, dest / "lumen-guest-boot.sh")
            try:
                os.chmod(dest / "lumen-guest-boot.sh", 0o755)
            except OSError:
                pass
    except OSError as exc:
        logger.warning("guest_agent_inject_failed: %s", type(exc).__name__)


def _write_project_drive(path: Path, project_path: str) -> None:
    """Pack project directory into an ext4 image for guest mount at /project."""
    src = Path(project_path)
    if not src.is_dir():
        raise RuntimeError(f"project_path_not_dir:{project_path}")
    _inject_guest_agent(src)
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


