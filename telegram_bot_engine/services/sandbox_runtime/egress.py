"""Real egress control for bot sandboxes.

TBE_EGRESS_MODE:
  strict   — iptables MUST apply private DROP + Telegram allow (default); else raise
  baseline — best-effort private DROP only
  proxy    — force bots to use HTTP(S)_PROXY; still try private DROP

When telegram-only is on (default), NEW connections not to DNS/Telegram IPs are DROPped.
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
from typing import List, Sequence

from .policy import load_policy

logger = logging.getLogger(__name__)

_PRIVATE_DROP = (
    "169.254.0.0/16",
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "100.64.0.0/10",
)


def _run(cmd: List[str], timeout: float = 20.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, (p.stderr or p.stdout or "")[:400]
    except Exception as exc:
        return 1, f"{type(exc).__name__}:{exc}"


def _egress_mode() -> str:
    return (os.environ.get("TBE_EGRESS_MODE") or "strict").strip().lower()


def _ensure_rule(check: List[str]) -> tuple[bool, str]:
    code, _ = _run(check)
    if code == 0:
        return True, "exists"
    ins = list(check)
    if len(ins) > 1 and ins[1] == "-C":
        ins[1] = "-I"
    code2, err = _run(ins)
    return code2 == 0, err


def resolve_allow_ips(hosts: Sequence[str]) -> List[str]:
    ips: List[str] = []
    for h in hosts:
        h = (h or "").strip()
        if not h:
            continue
        try:
            for info in socket.getaddrinfo(h, 443, type=socket.SOCK_STREAM):
                ip = info[4][0]
                if ip and ip not in ips:
                    ips.append(ip)
        except Exception as exc:
            logger.warning("egress resolve %s failed: %s", h, type(exc).__name__)
    return ips


def apply_egress_iptables(network_name: str, allow_hosts: Sequence[str]) -> dict:
    report: dict = {"ok": False, "rules": [], "errors": [], "allow_ips": []}
    if not shutil.which("iptables"):
        report["errors"].append("iptables_not_found")
        return report
    if (os.environ.get("TBE_EGRESS_IPTABLES") or "1").strip().lower() not in {"1", "true", "yes", "on"}:
        report["errors"].append("TBE_EGRESS_IPTABLES disabled")
        return report

    ok, err = _ensure_rule(
        ["iptables", "-C", "DOCKER-USER", "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT"]
    )
    report["rules"].append({"rule": "est", "ok": ok, "err": err})
    if not ok:
        report["errors"].append(f"est:{err}")

    for cidr in _PRIVATE_DROP:
        ok, err = _ensure_rule(["iptables", "-C", "DOCKER-USER", "-d", cidr, "-j", "DROP"])
        report["rules"].append({"rule": f"drop:{cidr}", "ok": ok, "err": err})
        if not ok:
            report["errors"].append(f"drop:{cidr}:{err}")

    telegram_only = (os.environ.get("TBE_EGRESS_TELEGRAM_ONLY") or "1").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if telegram_only and allow_hosts:
        ips = resolve_allow_ips(allow_hosts)
        report["allow_ips"] = ips
        if not ips:
            report["errors"].append("telegram_ips_unresolved")
        for ip in ips:
            ok, err = _ensure_rule(
                ["iptables", "-C", "DOCKER-USER", "-p", "tcp", "-d", ip, "--dport", "443", "-j", "ACCEPT"]
            )
            report["rules"].append({"rule": f"allow:{ip}", "ok": ok, "err": err})
            if not ok:
                report["errors"].append(f"allow:{ip}:{err}")
        for proto in ("udp", "tcp"):
            ok, err = _ensure_rule(
                ["iptables", "-C", "DOCKER-USER", "-p", proto, "--dport", "53", "-j", "ACCEPT"]
            )
            report["rules"].append({"rule": f"dns:{proto}", "ok": ok, "err": err})
            if not ok:
                report["errors"].append(f"dns:{proto}:{err}")
        ok, err = _ensure_rule(
            ["iptables", "-C", "DOCKER-USER", "-m", "conntrack", "--ctstate", "NEW", "-j", "DROP"]
        )
        report["rules"].append({"rule": "drop_new", "ok": ok, "err": err})
        if not ok:
            report["errors"].append(f"drop_new:{err}")

    report["ok"] = len(report["errors"]) == 0
    if report["ok"]:
        logger.info(
            "egress iptables applied network=%s mode=%s allow_ips=%s",
            network_name,
            _egress_mode(),
            report["allow_ips"][:8],
        )
    else:
        logger.error("egress iptables incomplete: %s", report["errors"][:6])
    return report


def harden_network(network_name: str = "") -> dict:
    """Create/select network and apply egress. Raises in strict mode on failure."""
    policy = load_policy()
    from .network import ensure_egress_network, network_exists

    mode = _egress_mode()
    name = ensure_egress_network(create_if_missing=True)
    if network_name and network_exists(network_name):
        name = network_name
    os.environ["TBE_DOCKER_NETWORK"] = name

    ipt: dict = {}
    if policy.require_egress_allowlist or mode in {"strict", "baseline", "proxy"}:
        ipt = apply_egress_iptables(name, sorted(policy.egress_hosts))

    if mode == "strict" and not ipt.get("ok"):
        raise RuntimeError(
            "egress_strict_failed: cannot install host firewall rules for bot network. "
            f"errors={ipt.get('errors', [])[:5]}. "
            "Need root/CAP_NET_ADMIN, or TBE_EGRESS_MODE=baseline for dev only."
        )

    if mode == "proxy":
        os.environ.setdefault("TBE_FORCE_BOT_PROXY", "1")

    return {
        "network": name,
        "mode": mode,
        "iptables": ipt,
        "egress_hosts": sorted(policy.egress_hosts),
    }
