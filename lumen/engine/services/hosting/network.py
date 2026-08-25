"""Docker egress network bootstrap for hosted bots.

Creates a dedicated bridge network named by TBE_DOCKER_NETWORK.
Operators MUST still apply host firewall / cloud security-group rules so
containers can only reach api.telegram.org (and DNS).

Example nftables/iptables policy is documented in docs/COMMERCIAL_HOSTING.md.
"""
from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger("tbe.hosting.network")


def network_name() -> str:
    return (os.environ.get("TBE_DOCKER_NETWORK") or "").strip()


def ensure_network() -> tuple[bool, str]:
    name = network_name()
    if not name:
        return False, "TBE_DOCKER_NETWORK unset"
    # validate name
    import re
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}", name):
        return False, "invalid_network_name"
    insp = subprocess.run(
        ["docker", "network", "inspect", name],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if insp.returncode == 0:
        return True, "exists"
    # isolated bridge — no external publish; egress controlled by host firewall
    create = subprocess.run(
        [
            "docker", "network", "create",
            "--driver", "bridge",
            "--opt", "com.docker.network.bridge.enable_icc=false",
            "--label", "tbe.managed=1",
            "--label", "tbe.role=bot-egress",
            name,
        ],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if create.returncode != 0:
        return False, (create.stderr or create.stdout or "create_failed")[:300]
    return True, "created"


def telegram_egress_hint() -> str:
    return (
        "Apply host firewall so this docker bridge may egress only to:\n"
        "  - DNS (53/tcp+udp)\n"
        "  - api.telegram.org 443/tcp\n"
        "Block link-local 169.254.0.0/16 and RFC1918 to your control plane."
    )
