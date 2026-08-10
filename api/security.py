"""API security helpers — path containment, safe errors."""
from __future__ import annotations

import os
from pathlib import Path

from telegram_bot_engine.services.user_sandbox import get_user_sandbox, shard_for_user


def output_root() -> Path:
    return Path(os.getenv("OUTPUT_DIR", "/tmp/generated")).resolve()


def tenant_sandbox_root(tenant_id: str) -> Path:
    """Filesystem root owned by a B2B tenant (mirrors user sandbox layout)."""
    uid = abs(hash(tenant_id)) % (10**9)
    return get_user_sandbox(uid, output_root()).root.resolve()


def is_path_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def validate_tenant_project_path(tenant_id: str, project_path: str) -> Path:
    """Resolve and enforce that project_path is inside the tenant sandbox.

    Rejects absolute escapes, relative traversal, and any path outside OUTPUT_DIR/users/...
    """
    if not project_path or not str(project_path).strip():
        raise ValueError("project_path_required")
    raw = str(project_path).strip()
    # Block null bytes and obvious traversal tokens before resolve
    if "\x00" in raw:
        raise ValueError("invalid_path")
    try:
        path = Path(raw).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError("invalid_path") from exc

    if not path.is_dir():
        raise ValueError("project_path_not_a_directory")

    sandbox = tenant_sandbox_root(tenant_id)
    # Also accept any path under OUTPUT_DIR/users/<shard>/<uid>/ for this tenant only
    if is_path_inside(path, sandbox):
        return path

    # Hard deny everything else (including /etc, other tenants, host app code)
    raise ValueError("project_path_outside_sandbox")


def validate_user_project_path(user_id: int, project_path: str) -> Path:
    """Same containment for Telegram consumer user_id."""
    if not project_path or not str(project_path).strip():
        raise ValueError("project_path_required")
    path = Path(str(project_path).strip()).resolve(strict=False)
    if not path.is_dir():
        raise ValueError("project_path_not_a_directory")
    sandbox = get_user_sandbox(int(user_id), output_root()).root.resolve()
    if not is_path_inside(path, sandbox):
        raise ValueError("project_path_outside_sandbox")
    return path
