"""API security helpers — path containment, safe errors."""
from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from b2b_platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.capability_maestro'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


import hashlib
import os
from pathlib import Path

from telegram_bot_engine.services.user_sandbox import get_user_sandbox, shard_for_user


def output_root() -> Path:
    return Path(os.getenv("OUTPUT_DIR") or _cm_default_output_dir()).resolve()


def stable_tenant_uid(tenant_id: str) -> int:
    """Deterministic sandbox user-id for a tenant.

    NEVER use built-in hash() — it is randomized per process (PYTHONHASHSEED),
    which would move sandboxes on every restart and orphan running bots.
    """
    digest = hashlib.sha256(str(tenant_id or "").encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % (10**9)


def tenant_sandbox_root(tenant_id: str) -> Path:
    """Filesystem root owned by a B2B tenant (mirrors user sandbox layout)."""
    uid = stable_tenant_uid(tenant_id)
    return get_user_sandbox(uid, output_root()).root.resolve()


def is_path_inside(child: Path, parent: Path) -> bool:
    """True if child is under parent after resolve; rejects symlink escapes."""
    try:
        c = child.resolve()
        p = parent.resolve()
        c.relative_to(p)
        # Reject if any path component is a symlink pointing outside parent
        cur = Path(c.anchor) if c.anchor else Path("/")
        for part in c.parts[1:]:
            cur = cur / part
            try:
                if cur.is_symlink():
                    target = cur.resolve()
                    target.relative_to(p)
            except (ValueError, OSError):
                return False
            # Stop walking at the final path
            if cur == c:
                break
        return True
    except (ValueError, OSError):
        return False


def _reject_unsafe_path_string(raw: str) -> None:
    """Hard-reject unsafe path tokens before resolve.

    Defense-in-depth: Path.resolve() + is_path_inside() remain the authority,
    but null bytes, traversal segments, and UNC paths are rejected immediately
    so malformed inputs never reach the filesystem layer.
    """
    if "\x00" in raw:
        raise ValueError("invalid_path")
    normalized = raw.replace("\\", "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("path_traversal_rejected")
    stripped = raw.strip()
    lower = stripped.lower()
    if lower.startswith("\\\\") or lower.startswith("//") or lower.startswith("file:"):
        raise ValueError("path_scheme_rejected")


def validate_tenant_project_path(tenant_id: str, project_path: str) -> Path:
    """Resolve and enforce that project_path is inside the tenant sandbox.

    Rejects absolute escapes, relative traversal, and any path outside OUTPUT_DIR/users/...
    """
    if not project_path or not str(project_path).strip():
        raise ValueError("project_path_required")
    raw = str(project_path).strip()
    _reject_unsafe_path_string(raw)
    try:
        path = Path(raw).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError("invalid_path") from exc

    if not path.is_dir():
        raise ValueError("project_path_not_a_directory")

    # Symlink project roots are forbidden (TOCTOU / path swap)
    try:
        if Path(raw).is_symlink() or path.is_symlink():
            raise ValueError("project_path_symlink_forbidden")
    except ValueError:
        raise
    except OSError:
        pass

    sandbox = tenant_sandbox_root(tenant_id)
    if is_path_inside(path, sandbox):
        return path

    raise ValueError("project_path_outside_sandbox")


def validate_user_project_path(user_id: int, project_path: str) -> Path:
    """Same containment for Telegram consumer user_id."""
    if not project_path or not str(project_path).strip():
        raise ValueError("project_path_required")
    raw = str(project_path).strip()
    _reject_unsafe_path_string(raw)
    try:
        path = Path(raw).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError("invalid_path") from exc
    if not path.is_dir():
        raise ValueError("project_path_not_a_directory")
    sandbox = get_user_sandbox(int(user_id), output_root()).root.resolve()
    if not is_path_inside(path, sandbox):
        raise ValueError("project_path_outside_sandbox")
    return path
