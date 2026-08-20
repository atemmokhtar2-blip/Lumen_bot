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


# Paths that must keep a raw body stream (custom size caps / signature verify).
# json_body_middleware MUST NOT consume these bodies.
RAW_BODY_PATHS = frozenset(
    {
        "/v1/billing/webhook/stripe",
        "/v1/generate",
    }
)


async def safe_json_body(
    request,
    *,
    required: bool = True,
    max_bytes: int = 65536,
) -> dict:
    """Parse JSON body safely: never raise unhandled errors to the client.

    Root contract:
    - Prefer request['json_body'] when json_body_middleware already parsed.
    - Invalid / non-object JSON → HTTP 400 with stable error code.
    - Empty body when required=False → {}.
    - Oversized declared Content-Length → 413 (defense in depth).

    Returns a dict only. Callers must not assume other JSON root types.
    """
    from aiohttp import web

    # Middleware already parsed → single source of truth (body stream consumed once)
    if request.get("json_body_parsed"):
        body = request.get("json_body")
        if body is None:
            if not required:
                return {}
            raise web.HTTPBadRequest(
                text='{"error":"invalid_json"}',
                content_type="application/json",
            )
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(
                text='{"error":"body_must_be_object"}',
                content_type="application/json",
            )
        return body

    cl = request.headers.get("Content-Length")
    if cl is not None:
        try:
            if int(cl) > max_bytes:
                raise web.HTTPRequestEntityTooLarge(
                    text='{"error":"payload_too_large"}',
                    content_type="application/json",
                )
        except ValueError:
            raise web.HTTPBadRequest(
                text='{"error":"invalid_content_length"}',
                content_type="application/json",
            )

    if not required and not request.can_read_body:
        request["json_body"] = {}
        request["json_body_parsed"] = True
        return {}

    try:
        body = await request.json()
    except Exception:
        if not required:
            request["json_body"] = {}
            request["json_body_parsed"] = True
            return {}
        raise web.HTTPBadRequest(
            text='{"error":"invalid_json"}',
            content_type="application/json",
        )

    if body is None:
        if not required:
            request["json_body"] = {}
            request["json_body_parsed"] = True
            return {}
        raise web.HTTPBadRequest(
            text='{"error":"invalid_json"}',
            content_type="application/json",
        )

    if not isinstance(body, dict):
        raise web.HTTPBadRequest(
            text='{"error":"body_must_be_object"}',
            content_type="application/json",
        )
    request["json_body"] = body
    request["json_body_parsed"] = True
    return body


def admin_token_matches(provided: str, expected: str) -> bool:
    """Constant-time comparison for PLATFORM_ADMIN_TOKEN (root hardening).

    Always compares fixed-size digests so neither presence nor length of the
    provided token can leak via early-return timing. Empty expected fails closed.
    """
    import hashlib
    import hmac

    exp = (expected or "").strip().encode("utf-8")
    got = (provided or "").strip().encode("utf-8")
    if not exp:
        return False
    # HMAC both sides under the expected secret as key → 32-byte digests always.
    # Equal iff got == exp (collision probability negligible for admin secrets).
    left = hmac.new(exp, got, hashlib.sha256).digest()
    right = hmac.new(exp, exp, hashlib.sha256).digest()
    return hmac.compare_digest(left, right)
