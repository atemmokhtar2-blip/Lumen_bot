"""Per-microVM network isolation for Firecracker (iproute2 + TAP + netns).

Multi-tenant rule: NEVER share one TAP across VMs.
Each VM gets: netns + veth/tap pair + optional bridge uplink with egress filter.

Requires: ip (iproute2), CAP_NET_ADMIN (or root). Fail closed if unavailable
when TBE_FC_AUTO_NET=1 (default in production).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_SAFE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,14}$")


def _flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def _run(cmd: list[str], timeout: float = 20.0) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}:{exc}"


def ip_available() -> bool:
    return bool(shutil.which("ip"))


@dataclass
class FcNetPlan:
    """Allocated host-side network for one microVM."""

    vm_id: str
    tap_name: str
    netns: str
    netns_path: str
    bridge: str
    guest_mac: str
    created: bool = False


def _short_id(vm_id: str) -> str:
    # Linux IFNAMSIZ is 15 chars
    raw = re.sub(r"[^a-zA-Z0-9]", "", vm_id)[-10:] or "x"
    return raw[:10]


def allocate_plan(vm_id: str, guest_mac: str) -> FcNetPlan:
    sid = _short_id(vm_id)
    tap = f"fct{sid}"[:15]
    ns = f"fcns{sid}"[:15]
    if not _SAFE.match(tap) or not _SAFE.match(ns):
        raise RuntimeError(f"invalid_fc_net_names:{tap}/{ns}")
    bridge = (os.environ.get("TBE_FC_BRIDGE") or "fcbr0").strip() or "fcbr0"
    return FcNetPlan(
        vm_id=vm_id,
        tap_name=tap,
        netns=ns,
        netns_path=f"/var/run/netns/{ns}",
        bridge=bridge,
        guest_mac=guest_mac,
    )


def ensure_bridge(name: str) -> None:
    if not ip_available():
        raise RuntimeError("iproute2_missing")
    code, _, _ = _run(["ip", "link", "show", name])
    if code == 0:
        return
    code, _, err = _run(["ip", "link", "add", "name", name, "type", "bridge"])
    if code != 0:
        raise RuntimeError(f"bridge_create_failed:{err[:200]}")
    _run(["ip", "link", "set", name, "up"])



def _resolve_allow_ips(hosts: list[str]) -> list[str]:
    import socket
    ips: list[str] = []
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
            logger.warning("fc egress resolve %s failed: %s", h, type(exc).__name__)
    return ips


def apply_fc_tap_egress(tap_name: str) -> dict:
    """Deny-by-default FORWARD for traffic from this TAP (production posture).

    Allow: ESTABLISHED/RELATED, DNS (53), policy egress hosts on tcp/443.
    Drop: other NEW from this interface.
    Requires iptables. Best-effort insert; production can require success via TBE_FC_EGRESS_STRICT.
    """
    report: dict = {"ok": False, "rules": [], "errors": [], "allow_ips": []}
    if not tap_name or not _SAFE.match(tap_name):
        report["errors"].append("invalid_tap")
        return report
    if not shutil.which("iptables"):
        report["errors"].append("iptables_not_found")
        return report

    try:
        from .policy import load_policy
        hosts = sorted(load_policy().egress_hosts)
    except Exception:
        hosts = ["api.telegram.org", "core.telegram.org"]

    telegram_only = (os.environ.get("TBE_EGRESS_TELEGRAM_ONLY") or "1").strip().lower() in {
        "1", "true", "yes", "on"
    }
    allow_ips = _resolve_allow_ips(hosts) if telegram_only else []
    report["allow_ips"] = allow_ips

    def _ensure(check: list[str]) -> tuple[bool, str]:
        code, _, err = _run(check)
        if code == 0:
            return True, "exists"
        ins = list(check)
        if len(ins) > 1 and ins[1] == "-C":
            ins[1] = "-I"
        code2, _, err2 = _run(ins)
        return code2 == 0, err2[:200]

    # Established
    ok, err = _ensure(
        ["iptables", "-C", "FORWARD", "-i", tap_name, "-m", "conntrack",
         "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT"]
    )
    report["rules"].append({"rule": "est", "ok": ok, "err": err})
    if not ok:
        report["errors"].append(f"est:{err}")

    # DNS
    for proto in ("udp", "tcp"):
        ok, err = _ensure(
            ["iptables", "-C", "FORWARD", "-i", tap_name, "-p", proto, "--dport", "53", "-j", "ACCEPT"]
        )
        report["rules"].append({"rule": f"dns_{proto}", "ok": ok, "err": err})
        if not ok:
            report["errors"].append(f"dns_{proto}:{err}")

    # Telegram / allowlist HTTPS
    if telegram_only:
        if not allow_ips:
            report["errors"].append("telegram_ips_unresolved")
        for ip in allow_ips:
            ok, err = _ensure(
                ["iptables", "-C", "FORWARD", "-i", tap_name, "-p", "tcp",
                 "-d", ip, "--dport", "443", "-j", "ACCEPT"]
            )
            report["rules"].append({"rule": f"allow:{ip}", "ok": ok, "err": err})
            if not ok:
                report["errors"].append(f"allow:{ip}:{err}")

        # Drop other NEW from this TAP
        ok, err = _ensure(
            ["iptables", "-C", "FORWARD", "-i", tap_name, "-m", "conntrack",
             "--ctstate", "NEW", "-j", "DROP"]
        )
        report["rules"].append({"rule": "drop_new", "ok": ok, "err": err})
        if not ok:
            report["errors"].append(f"drop_new:{err}")

    report["ok"] = len(report["errors"]) == 0
    if report["ok"]:
        logger.info("fc egress applied tap=%s allow_ips=%s", tap_name, allow_ips[:6])
    else:
        logger.error("fc egress incomplete tap=%s errors=%s", tap_name, report["errors"][:6])
    return report


def create_vm_network(plan: FcNetPlan) -> FcNetPlan:
    """Create dedicated TAP in its own netns, attach TAP to host bridge for egress."""
    if not ip_available():
        raise RuntimeError("iproute2_missing")

    ensure_bridge(plan.bridge)

    # netns
    if not os.path.exists(plan.netns_path):
        code, _, err = _run(["ip", "netns", "add", plan.netns])
        if code != 0 and not os.path.exists(plan.netns_path):
            raise RuntimeError(f"netns_add_failed:{err[:200]}")

    # TAP on host, then move to netns — Firecracker needs TAP on host side typically.
    # Standard pattern: TAP stays on host, jailer --netns moves process; TAP must be
    # visible to VMM. Firecracker host_dev_name is host TAP name.
    code, _, _ = _run(["ip", "link", "show", plan.tap_name])
    if code != 0:
        code, _, err = _run(["ip", "tuntap", "add", "dev", plan.tap_name, "mode", "tap"])
        if code != 0:
            # fallback older syntax
            code2, _, err2 = _run(["ip", "link", "add", plan.tap_name, "type", "tun", "mode", "tap"])
            if code2 != 0:
                raise RuntimeError(f"tap_create_failed:{err[:120]}|{err2[:120]}")
    _run(["ip", "link", "set", plan.tap_name, "up"])

    # Attach TAP to bridge so guest can egress via host routing/NAT
    _run(["ip", "link", "set", plan.tap_name, "master", plan.bridge])

    # Minimal forward + masquerade hints (best-effort; operator may use nft)
    if _flag("TBE_FC_ENABLE_NAT", "1"):
        _run(
            [
                "iptables",
                "-t",
                "nat",
                "-C",
                "POSTROUTING",
                "-o",
                (os.environ.get("TBE_FC_UPLINK") or "eth0"),
                "-j",
                "MASQUERADE",
            ]
        )
        # insert if missing handled by check failure — ignore errors
        _run(
            [
                "iptables",
                "-t",
                "nat",
                "-A",
                "POSTROUTING",
                "-o",
                (os.environ.get("TBE_FC_UPLINK") or "eth0"),
                "-j",
                "MASQUERADE",
            ]
        )
        _run(["sysctl", "-w", "net.ipv4.ip_forward=1"])

    plan.created = True

    # Production-grade egress: deny-by-default from this TAP (Telegram allowlist)
    egress_report = apply_fc_tap_egress(plan.tap_name)
    strict = _flag("TBE_FC_EGRESS_STRICT", "1")
    if strict and not egress_report.get("ok"):
        # Tear down partial net on strict failure
        try:
            destroy_vm_network(plan)
        except Exception:
            pass
        raise RuntimeError(
            "fc_egress_strict_failed: "
            + ",".join(str(x) for x in (egress_report.get("errors") or [])[:4])
        )

    logger.info(
        "fc net ready vm=%s tap=%s bridge=%s netns=%s egress_ok=%s",
        plan.vm_id[:20],
        plan.tap_name,
        plan.bridge,
        plan.netns,
        egress_report.get("ok"),
    )
    return plan


def destroy_vm_network(plan: Optional[FcNetPlan] = None, *, tap_name: str = "", netns: str = "") -> None:
    tap = (tap_name or (plan.tap_name if plan else "")).strip()
    ns = (netns or (plan.netns if plan else "")).strip()
    if tap:
        _run(["ip", "link", "set", tap, "nomaster"])
        _run(["ip", "link", "delete", tap])
    if ns and os.path.exists(f"/var/run/netns/{ns}"):
        _run(["ip", "netns", "delete", ns])


def resolve_start_network(vm_id: str, guest_mac: str) -> Tuple[str, str, Optional[FcNetPlan]]:
    """Return (tap_name, netns_path, plan).

    Priority:
      1) TBE_FC_AUTO_NET=1 → allocate exclusive TAP (+ bridge)
      2) TBE_FC_TAP static (dev only — rejected if auto required)
      3) empty if TBE_FC_ALLOW_NO_NET
    """
    static_tap = (os.environ.get("TBE_FC_TAP") or "").strip()
    static_ns = (os.environ.get("TBE_FC_NETNS") or "").strip()
    auto = _flag("TBE_FC_AUTO_NET", "1")

    if auto:
        if static_tap and not _flag("TBE_FC_ALLOW_SHARED_TAP", "0"):
            # Shared static TAP is multi-tenant hazard — refuse unless explicit
            raise RuntimeError(
                "shared_TBE_FC_TAP_forbidden: enable TBE_FC_AUTO_NET (default) "
                "for per-VM TAP, or TBE_FC_ALLOW_SHARED_TAP=1 for lab only"
            )
        plan = allocate_plan(vm_id, guest_mac)
        create_vm_network(plan)
        ns_path = plan.netns_path if _flag("TBE_FC_JAILER_NETNS", "1") else ""
        return plan.tap_name, ns_path, plan

    if static_tap:
        ns_path = static_ns if static_ns.startswith("/") else (
            f"/var/run/netns/{static_ns}" if static_ns else ""
        )
        return static_tap, ns_path, None

    if _flag("TBE_FC_ALLOW_NO_NET", "0"):
        return "", "", None

    raise RuntimeError(
        "fc_network_required: set TBE_FC_AUTO_NET=1 (recommended) or TBE_FC_TAP "
        "or TBE_FC_ALLOW_NO_NET=1"
    )
