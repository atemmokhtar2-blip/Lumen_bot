"""Ephemeral Docker-isolated git clone for untrusted remotes.

When Docker is available (default preference):
  - non-root user
  - no host network except what the container image allows
  - core.hooksPath disabled
  - result copied to host destination; container removed

Falls back to host git only when TBE_GIT_CLONE_ALLOW_HOST=1 (dev),
still with hooks disabled via secure_exec.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("tbe.git_clone_isolated")

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9._/-]+$")


def _docker_ok() -> bool:
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def prefer_docker_clone() -> bool:
    raw = (os.getenv("TBE_GIT_CLONE_DOCKER") or "1").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return _docker_ok()


def clone_isolated(
    url: str,
    dest: Path,
    *,
    branch: str | None = None,
    depth: int = 1,
    timeout: int = 180,
) -> tuple[bool, str]:
    """Clone url into dest using ephemeral container when possible."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if prefer_docker_clone():
        ok, msg = _clone_via_docker(url, dest, branch=branch, depth=depth, timeout=timeout)
        if ok:
            return ok, msg
        # no host fallback unless explicit
        allow_host = (os.getenv("TBE_GIT_CLONE_ALLOW_HOST") or "").strip().lower() in {
            "1", "true", "yes", "on",
        }
        if not allow_host:
            return False, msg or "docker_clone_failed"
        # fall through to host only when allowed

    allow_host = (os.getenv("TBE_GIT_CLONE_ALLOW_HOST") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if not allow_host:
        return False, "docker_required_for_git_clone"

    # Host path: still hooks-disabled via run_git
    from telegram_bot_engine.services.secure_exec import run_git, neutralize_git_hooks

    args = ["git", "clone", "--single-branch", "--no-tags"]
    if depth > 0:
        args += ["--depth", str(depth)]
    if branch:
        args += ["--branch", branch]
    args += [url, str(dest)]
    proc = run_git(args, timeout=timeout)
    if proc.returncode != 0:
        err = ((proc.stderr or "") + (proc.stdout or ""))[:400]
        return False, f"host_clone_failed:{err}"
    neutralize_git_hooks(dest)
    return True, "host_clone_ok"


def _clone_via_docker(
    url: str,
    dest: Path,
    *,
    branch: str | None,
    depth: int,
    timeout: int,
) -> tuple[bool, str]:
    """Run alpine/git in a throwaway container; copy worktree out."""
    image = (os.getenv("TBE_GIT_CLONE_IMAGE") or "alpine/git:latest").strip()
    work = tempfile.mkdtemp(prefix="tbe_git_")
    try:
        # Network required to reach git host; no host mounts of secrets
        cmd = [
            "docker", "run", "--rm",
            "--network", (os.getenv("TBE_GIT_CLONE_NETWORK") or "bridge"),
            "--user", "10001:10001",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--memory", "512m",
            "--cpus", "1",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",
            "-v", f"{work}:/work",
            "-w", "/work",
            image,
            "-c", "core.hooksPath=/dev/null",
            "-c", "protocol.file.allow=never",
            "clone", "--single-branch", "--no-tags",
        ]
        if depth > 0:
            cmd += ["--depth", str(depth)]
        if branch:
            cmd += ["--branch", branch]
        cmd += [url, "repo"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        if proc.returncode != 0:
            err = ((proc.stderr or "") + (proc.stdout or ""))[:400]
            return False, f"docker_clone_failed:{err}"
        src = Path(work) / "repo"
        if not src.is_dir():
            return False, "docker_clone_missing_workdir"
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, symlinks=False)
        from telegram_bot_engine.services.secure_exec import neutralize_git_hooks
        neutralize_git_hooks(dest)
        return True, "docker_clone_ok"
    except subprocess.TimeoutExpired:
        return False, "docker_clone_timeout"
    except Exception as exc:
        return False, f"docker_clone_error:{type(exc).__name__}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
