"""Egress allowlist enforcement for bot containers.

Creates/uses a dedicated bridge and applies iptables DOCKER-USER rules when
the host permits (Linux + CAP_NET_ADMIN). Without iptables, still refuses
default bridge and attaches bots only to TBE_DOCKER_NETWORK.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import List, Sequence

from .policy import load_policy

logger = logging.getLogger(__name__)


def _run(cmd: List[str], timeout: float = 20.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, (p.stderr or p.stdout or "")[:400]
    except Exception as exc:
        return 1, f"{type(exc).__name__}:{exc}"


def apply_egress_iptables(network_name: str, allow_hosts: Sequence[str]) -> dict:
    """Best-effort DOCKER-USER baseline. Fail-soft with report."""
    report: dict = {"ok": False, "rules": [], "errors": []}
    if not shutil.which("iptables"):
        report["errors"].append("iptables_not_found")
        return report
    if (os.environ.get("TBE_EGRESS_IPTABLES") or "1").strip().lower() not in {"1", "true", "yes", "on"}:
        report["errors"].append("TBE_EGRESS_IPTABLES disabled")
        return report

    rules = [
        ["iptables", "-C", "DOCKER-USER", "-d", "169.254.169.254", "-j", "DROP"],
        ["iptables", "-C", "DOCKER-USER", "-d", "127.0.0.0/8", "-j", "DROP"],
    ]
    # -C checks; if missing, -I insert
    for check in rules:
        code, _ = _run(check)
        if code != 0:
            ins = list(check)
            ins[1] = "-I"
            code2, err = _run(ins)
            report["rules"].append({"cmd": ins, "code": code2, "err": err})
            if code2 != 0:
                report["errors"].append(err)
        else:
            report["rules"].append({"cmd": check, "code": 0, "err": "already"})
    report["ok"] = len(report["errors"]) == 0
    if report["ok"]:
        logger.info(
            "egress iptables baseline applied network=%s hosts=%s",
            network_name,
            list(allow_hosts)[:8],
        )
    return report


def harden_network(network_name: str = "") -> dict:
    policy = load_policy()
    from .network import ensure_egress_network, network_exists

    name = ensure_egress_network(create_if_missing=True)
    if network_name and network_exists(network_name):
        name = network_name
    os.environ["TBE_DOCKER_NETWORK"] = name
    ipt: dict = {}
    if policy.require_egress_allowlist:
        ipt = apply_egress_iptables(name, sorted(policy.egress_hosts))
    return {"network": name, "iptables": ipt, "egress_hosts": sorted(policy.egress_hosts)}
