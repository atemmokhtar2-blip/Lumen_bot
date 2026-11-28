"""Multi-tenant isolation helpers (Phase D hardening).

Goals:
  - Host instances always bound to tenant_id + user_id
  - Redis keys namespaced by tenant when known
  - Firecracker state directories never shared across tenants/users
  - Project paths verified with openat2 / no-symlink where available
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumen.tenant_isolation")


def safe_tenant_segment(tenant_id: str) -> str:
    """Opaque collision-resistant namespace for tenant-owned paths and keys."""
    tenant = str(tenant_id or "").strip()
    if not tenant or len(tenant) > 256:
        raise ValueError("invalid_tenant_id")
    return "t_" + hashlib.sha256(tenant.encode("utf-8")).hexdigest()


def host_instance_redis_key(instance_id: str, *, tenant_id: str = "") -> str:
    iid = (instance_id or "").strip()
    if tenant_id:
        return f"lumen:host:t:{safe_tenant_segment(tenant_id)}:inst:{iid}"
    return f"lumen:host:inst:{iid}"


def host_user_index_key(user_id: int, *, tenant_id: str = "") -> str:
    if tenant_id:
        return f"lumen:host:t:{safe_tenant_segment(tenant_id)}:user:{int(user_id)}"
    return f"lumen:host:user:{int(user_id)}"


def firecracker_state_dir(*, user_id: int = 0, tenant_id: str = "") -> Path:
    """Per-tenant/user Firecracker metadata — never a flat shared pool."""
    base = Path(
        os.environ.get("TBE_FC_STATE_DIR")
        or os.path.join(os.environ.get("OUTPUT_DIR") or "/tmp", "fc_vms")
    )
    parts: list[str] = []
    if tenant_id:
        parts.append(safe_tenant_segment(tenant_id))
    if user_id:
        parts.append(f"u_{int(user_id)}")
    if not parts:
        # Fail closed in production: refuse global shared dir
        try:
            from lumen.platform.prod_security_gate import is_production_runtime

            if is_production_runtime():
                raise RuntimeError(
                    "firecracker_state_dir requires user_id or tenant_id in production"
                )
        except RuntimeError:
            raise
        except Exception:
            pass
        parts.append("_shared_dev")
    path = base.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except Exception:
        pass
    return path


def assert_instance_owner(
    inst: Any,
    *,
    user_id: int | None = None,
    tenant_id: str = "",
) -> bool:
    """True only if inst is owned by the caller (tenant and/or user)."""
    if inst is None:
        return False
    if user_id is not None and int(getattr(inst, "user_id", -1) or -1) != int(user_id):
        return False
    want_t = (tenant_id or "").strip()
    got_t = (getattr(inst, "tenant_id", None) or "").strip()
    if want_t:
        # Tenant-owned instances require an exact tenant match in every env.
        if got_t != want_t:
            return False
    elif got_t:
        # A Telegram/user-scoped lookup must never see a tenant-bound instance,
        # even when the numeric surrogate user_id happens to collide.
        return False
    return True


def verify_project_under_owner(
    *,
    user_id: int,
    project_path: str | Path,
    tenant_id: str = "",
    base_dir: str | Path | None = None,
) -> Path:
    """Resolve + contain project path under the owner's sandbox (no symlink escape).

    ``base_dir`` must match HostService.output_root / bot OUTPUT_DIR — never guess a
    different root (that was a real isolation false-reject / false-accept bug).
    """
    from lumen.engine.services.user_sandbox import get_tenant_sandbox, get_user_sandbox

    if base_dir is not None:
        base = base_dir
    else:
        try:
            from lumen.platform.paths import default_output_dir
            base = default_output_dir()
        except Exception:
            base = os.environ.get("OUTPUT_DIR") or "/tmp"

    sandbox = (
        get_tenant_sandbox(tenant_id, base)
        if (tenant_id or "").strip()
        else get_user_sandbox(int(user_id), base)
    )
    sandbox.ensure()
    root = sandbox.root.resolve()
    raw = str(project_path or "").strip()
    if not raw:
        raise ValueError("project_path_required")
    if "\x00" in raw:
        raise ValueError("null_byte_in_path")

    path = Path(raw).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("project_path_outside_sandbox") from exc

    # openat2 / O_NOFOLLOW when available
    try:
        from lumen.engine.services.linux_path_open import verify_dir_beneath
        from lumen.api.security import _require_openat2

        verified = verify_dir_beneath(
            root, path, require_openat2=_require_openat2()
        )
        path = Path(verified)
        path.relative_to(root)
    except Exception as exc:
        # Verification errors are never downgraded to pathlib-only acceptance.
        raise ValueError("project_path_symlink_or_escape") from exc
    return path


__all__ = [
    "safe_tenant_segment",
    "host_instance_redis_key",
    "host_user_index_key",
    "firecracker_state_dir",
    "assert_instance_owner",
    "verify_project_under_owner",
]
