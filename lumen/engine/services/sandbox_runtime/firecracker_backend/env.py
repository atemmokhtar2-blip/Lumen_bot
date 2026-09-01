"""Firecracker environment, binaries, and isolation policy."""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

_FC_UID_BASE = 200000
_FC_UID_SPAN = 100000

def _flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def _is_dev_environment() -> bool:
    """True only for explicit local/dev/test — never when deploy signals present."""
    markers = (
        "KUBERNETES_SERVICE_HOST",
        "K_SERVICE",
        "AWS_EXECUTION_ENV",
        "AWS_REGION",
        "RAILWAY_ENVIRONMENT",
        "RENDER_SERVICE_ID",
        "FLY_APP_NAME",
        "DYNO",
        "WEBSITE_INSTANCE_ID",
    )
    for m in markers:
        if (os.getenv(m) or "").strip():
            return False
    if (os.getenv("FORCE_PRODUCTION") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    return env in {"dev", "development", "local", "test"}


def _bin() -> str:
    return (os.environ.get("TBE_FIRECRACKER_BIN") or shutil.which("firecracker") or "").strip()


def _jailer_bin() -> str:
    return (os.environ.get("TBE_JAILER_BIN") or shutil.which("jailer") or "").strip()


def _kernel() -> str:
    return (os.environ.get("TBE_FC_KERNEL") or "").strip()


def _rootfs() -> str:
    return (os.environ.get("TBE_FC_ROOTFS") or "").strip()


def _kvm_ok() -> bool:
    return os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)


def _chroot_base() -> Path:
    raw = (os.environ.get("TBE_FC_CHROOT_BASE") or "/srv/jailer").strip()
    return Path(raw)


def _production_isolation() -> bool:
    """Match select.is_production_sandbox_path — multi-tenant or non-dev."""
    try:
        from lumen.engine.services.sandbox_runtime.select import is_production_sandbox_path
        return is_production_sandbox_path()
    except Exception:
        # Fail closed: treat as production if we cannot import
        if not _is_dev_environment():
            return True
        multi = (os.environ.get("TBE_MULTI_TENANT") or "1").strip().lower() in {
            "1", "true", "yes", "on"
        }
        return multi


def _require_jailer() -> bool:
    """Jailer is mandatory on the production isolation path.

    Dev may opt out only with BOTH:
      ENVIRONMENT=dev|local|test AND TBE_FC_ALLOW_NO_JAILER=1
    TBE_FC_REQUIRE_JAILER=0 is ignored when production isolation applies.
    """
    if _production_isolation():
        return True
    # Dev path only
    if _flag("TBE_FC_ALLOW_NO_JAILER", "0"):
        return False
    return _flag("TBE_FC_REQUIRE_JAILER", "1")


def _stable_vm_ids(user_id: int, vm_id: str) -> Tuple[int, int]:
    """Deterministic unique uid/gid in reserved range for this microVM."""
    digest = hashlib.sha256(f"{user_id}:{vm_id}".encode()).hexdigest()
    offset = int(digest[:8], 16) % _FC_UID_SPAN
    uid = _FC_UID_BASE + offset
    gid = uid
    return uid, gid


