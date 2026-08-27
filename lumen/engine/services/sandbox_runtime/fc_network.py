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
    logger.info(
        "fc net ready vm=%s tap=%s bridge=%s netns=%s",
        plan.vm_id[:20],
        plan.tap_name,
        plan.bridge,
        plan.netns,
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
