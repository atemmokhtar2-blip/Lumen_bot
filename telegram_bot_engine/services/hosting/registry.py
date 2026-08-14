"""Container registry helpers for multi-node image distribution.

Env:
  TBE_DOCKER_REGISTRY=registry.example.com
  TBE_REGISTRY_USER=
  TBE_REGISTRY_PASSWORD=
  # or TBE_REGISTRY_PASSWORD_FILE=/run/secrets/registry_password
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("tbe.hosting.registry")


def registry_host() -> str:
    return (os.environ.get("TBE_DOCKER_REGISTRY") or "").strip().rstrip("/")


def _password() -> str:
    path = (os.environ.get("TBE_REGISTRY_PASSWORD_FILE") or "").strip()
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").strip()
    return (os.environ.get("TBE_REGISTRY_PASSWORD") or "").strip()


def docker_login() -> tuple[bool, str]:
    host = registry_host()
    if not host:
        return False, "TBE_DOCKER_REGISTRY unset"
    user = (os.environ.get("TBE_REGISTRY_USER") or "").strip()
    password = _password()
    if not user or not password:
        # Public registry or pre-authed host — treat as soft ok
        return True, "no_creds_assume_preauthed"
    try:
        proc = subprocess.run(
            ["docker", "login", host, "-u", user, "--password-stdin"],
            input=password,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception as e:
        return False, f"login_error:{type(e).__name__}:{e}"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "login_failed")[:300]
    return True, "login_ok"


def verify_push_pull(tag: str) -> tuple[bool, str]:
    """Push then pull a tag to validate registry path (expensive — use sparingly)."""
    ok, msg = docker_login()
    if not ok:
        return False, msg
    push = subprocess.run(["docker", "push", tag], capture_output=True, text=True, timeout=300, check=False)
    if push.returncode != 0:
        return False, (push.stderr or "")[:300]
    # remove local and pull back
    subprocess.run(["docker", "rmi", tag], capture_output=True, text=True, timeout=60, check=False)
    pull = subprocess.run(["docker", "pull", tag], capture_output=True, text=True, timeout=300, check=False)
    if pull.returncode != 0:
        return False, (pull.stderr or "")[:300]
    return True, "push_pull_ok"
