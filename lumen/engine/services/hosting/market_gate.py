"""Market-readiness gate for paid hosting.

Hosting is refused unless the deployment surface meets a minimum bar that
is safe to sell. Dev/local can set TBE_MARKET_GATE=0 to skip.

Commercial isolation track (sole path):
  Firecracker microVM — firecracker+jailer, TBE_FC_KERNEL, TBE_FC_ROOTFS,
  TAP or netns (TBE_FC_AUTO_NET / TBE_FC_TAP / TBE_FC_NETNS)

gVisor / DinD / Docker are NOT commercial tracks. They exist only for
explicit dev/local testing (TBE_SANDBOX_BACKEND=gvisor|dind|docker +
ENVIRONMENT=dev|local|test).

Shared requirements:
  TBE_TOKEN_SECRET (>=32), TBE_SCALE_MODE=1, Postgres control plane,
  no LocalProcess.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


def _on(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def _env() -> str:
    return (os.environ.get("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()


@dataclass
class GateResult:
    ok: bool
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    track: str = ""

    def message_ar(self) -> str:
        if self.ok:
            return f"بوابة السوق: جاهز ({self.track or 'ok'})"
        lines = ["الاستضافة التجارية غير مفعّلة — ينقص:"]
        for m in self.missing:
            lines.append(f"• {m}")
        if self.warnings:
            lines.append("تحذيرات:")
            for w in self.warnings:
                lines.append(f"• {w}")
        lines.append("اضبط المتغيرات ثم شغّل عمال: python -m lumen.engine.services.hosting.worker")
        return "\n".join(lines)


def market_gate_enabled() -> bool:
    if "TBE_MARKET_GATE" in os.environ:
        return _on("TBE_MARKET_GATE", "1")
    return _env() not in {"dev", "development", "local", "test"}


def _backend_pref() -> str:
    return (os.environ.get("TBE_SANDBOX_BACKEND") or "auto").strip().lower()


def _firecracker_track_ready() -> tuple[bool, list[str]]:
    missing: list[str] = []
    fc = (os.environ.get("TBE_FIRECRACKER_BIN") or shutil.which("firecracker") or "").strip()
    jailer = (os.environ.get("TBE_JAILER_BIN") or shutil.which("jailer") or "").strip()
    kernel = (os.environ.get("TBE_FC_KERNEL") or "").strip()
    rootfs = (os.environ.get("TBE_FC_ROOTFS") or "").strip()
    if not fc:
        missing.append("TBE_FIRECRACKER_BIN / firecracker")
    if not jailer and _on("TBE_FC_REQUIRE_JAILER", "1"):
        missing.append("TBE_JAILER_BIN / jailer (إلزامي في الإنتاج)")
    if not kernel or not Path(kernel).is_file():
        missing.append("TBE_FC_KERNEL (vmlinux موجود)")
    if not rootfs or not Path(rootfs).is_file():
        missing.append("TBE_FC_ROOTFS (rootfs.ext4 موجود)")
    auto_net = _on("TBE_FC_AUTO_NET", "1")
    tap = (os.environ.get("TBE_FC_TAP") or "").strip()
    netns = (os.environ.get("TBE_FC_NETNS") or "").strip()
    allow_no_net = _on("TBE_FC_ALLOW_NO_NET", "0")
    if not auto_net and not tap and not netns and not allow_no_net:
        missing.append("TBE_FC_AUTO_NET=1 أو TBE_FC_TAP أو TBE_FC_NETNS")
    if _on("TBE_FC_TOKEN_IN_BOOTARGS", "0"):
        missing.append("TBE_FC_TOKEN_IN_BOOTARGS يجب أن يكون 0 في الإنتاج")
    return (len(missing) == 0), missing


def evaluate_market_gate() -> GateResult:
    if not market_gate_enabled():
        return GateResult(ok=True, warnings=["market_gate_skipped_dev"], track="dev")

    missing: list[str] = []
    warnings: list[str] = []

    secret = (os.environ.get("TBE_TOKEN_SECRET") or "").strip()
    if len(secret) < 32:
        missing.append("TBE_TOKEN_SECRET (32+ حرف)")

    if not _on("TBE_SCALE_MODE", "0"):
        missing.append("TBE_SCALE_MODE=1 (طابور + workers — إلزامي للبيع)")

    db = (os.environ.get("TBE_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip().lower()
    if not (db.startswith("postgres://") or db.startswith("postgresql://")):
        missing.append("TBE_DATABASE_URL=postgresql://... (Postgres للتحكم)")

    if _on("TBE_ALLOW_LOCAL_PROCESS", "0"):
        missing.append("TBE_ALLOW_LOCAL_PROCESS يجب أن يكون 0")

    pref = _backend_pref()
    if pref in {"gvisor", "dind", "docker"}:
        missing.append(
            f"TBE_SANDBOX_BACKEND={pref} غير مقبول تجارياً — "
            "المسار التجاري الوحيد هو Firecracker "
            "(اضبط TBE_SANDBOX_BACKEND=firecracker أو auto)"
        )
        return GateResult(ok=False, missing=missing, warnings=warnings, track="rejected")

    fc_ok, fc_miss = _firecracker_track_ready()
    if not fc_ok:
        missing.extend(fc_miss)

    return GateResult(
        ok=not missing,
        missing=missing,
        warnings=warnings,
        track="firecracker",
    )
