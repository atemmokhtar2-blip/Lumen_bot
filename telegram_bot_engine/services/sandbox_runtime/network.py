"""Egress-limited Docker network for generated bots.

Bots must never share the default bridge. Operator sets TBE_DOCKER_NETWORK
to an existing network, or we create a dedicated one when allowed.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_SAFE_NET = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$")


def configured_network_name() -> str:
    return (os.environ.get("TBE_DOCKER_NETWORK") or "").strip()


def _run(cmd: list[str], timeout: float = 30.0) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}:{exc}"


def network_exists(name: str) -> bool:
    if not name or not shutil.which("docker"):
        return False
    code, out, _ = _run(["docker", "network", "inspect", name], timeout=15)
    return code == 0 and bool(out.strip())


def ensure_egress_network(*, create_if_missing: bool = True) -> str:
    """Return network name suitable for bot containers.

    Raises RuntimeError if policy cannot be satisfied (fail-closed).
    """
    name = configured_network_name()
    if not name:
        # Default dedicated name — still must be created explicitly unless allowed
        name = (os.environ.get("TBE_SANDBOX_NETWORK_DEFAULT") or "tbe-egress").strip()
    if not _SAFE_NET.match(name):
        raise RuntimeError(f"invalid_docker_network_name:{name}")

    if network_exists(name):
        return name

    allow_create = (os.environ.get("TBE_SANDBOX_CREATE_NETWORK") or "1").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if not create_if_missing or not allow_create:
        raise RuntimeError(
            f"docker_network_missing:{name} — create an egress-limited network "
            f"and set TBE_DOCKER_NETWORK={name}"
        )

    # Internal=false so bots can reach Telegram API; operator should attach
    # firewall / egress proxy. We still isolate from host bridge default.
    code, _, err = _run(
        [
            "docker", "network", "create",
            "--driver", "bridge",
            "--opt", "com.docker.network.bridge.enable_icc=false",
            "--label", "tbe.managed=1",
            "--label", "tbe.role=egress",
            name,
        ],
        timeout=45,
    )
    if code != 0 and not network_exists(name):
        raise RuntimeError(f"docker_network_create_failed:{err[:300]}")
    logger.info("sandbox network ready name=%s", name)
    return name


def seccomp_profile_path() -> Optional[str]:
    """Path to seccomp JSON for bot containers."""
    env = (os.environ.get("TBE_DOCKER_SECCOMP") or "").strip()
    if env:
        return env if os.path.isfile(env) else None
    here = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "sandbox", "seccomp-bot.json"
    )
    path = os.path.normpath(here)
    return path if os.path.isfile(path) else None
