"""API security helpers — path containment, safe errors."""
from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from lumen.platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.lumen'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


import hashlib
import os
from pathlib import Path

from lumen.engine.services.user_sandbox import get_user_sandbox, shard_for_user


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

    Anti-TOCTOU: final authority is Linux openat2(RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS)
    (fallback: O_DIRECTORY|O_NOFOLLOW). Never pathlib.is_symlink() alone.
    """
    if not project_path or not str(project_path).strip():
        raise ValueError("project_path_required")
    raw = str(project_path).strip()
    _reject_unsafe_path_string(raw)
    try:
        path = Path(raw).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError("invalid_path") from exc

    sandbox = tenant_sandbox_root(tenant_id)
    if not is_path_inside(path, sandbox):
        raise ValueError("project_path_outside_sandbox")

    try:
        # Kernel authority: openat2(RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS) when available
        from lumen.engine.services.linux_path_open import verify_dir_beneath, PathOpenError
        verified = verify_dir_beneath(sandbox, path, require_openat2=False)
    except Exception as exc:
        msg = str(exc).lower()
        if "not_a_directory" in msg or "enotdir" in msg:
            raise ValueError("project_path_not_a_directory") from exc
        raise ValueError("project_path_symlink_forbidden") from exc

    if not is_path_inside(Path(verified), sandbox):
        raise ValueError("project_path_outside_sandbox")
    return Path(verified)


def validate_user_project_path(user_id: int, project_path: str) -> Path:
    """Same containment for Telegram consumer user_id.

    Anti-TOCTOU: O_DIRECTORY|O_NOFOLLOW at use time (see validate_tenant_project_path).
    """
    if not project_path or not str(project_path).strip():
        raise ValueError("project_path_required")
    raw = str(project_path).strip()
    _reject_unsafe_path_string(raw)
    try:
        path = Path(raw).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError("invalid_path") from exc
    sandbox = get_user_sandbox(int(user_id), output_root()).root.resolve()
    if not is_path_inside(path, sandbox):
        raise ValueError("project_path_outside_sandbox")
    try:
        from lumen.engine.services.linux_path_open import verify_dir_beneath
        verified = verify_dir_beneath(sandbox, path, require_openat2=False)
    except Exception as exc:
        msg = str(exc).lower()
        if "not_a_directory" in msg or "enotdir" in msg:
            raise ValueError("project_path_not_a_directory") from exc
        raise ValueError("project_path_symlink_forbidden") from exc
    if not is_path_inside(Path(verified), sandbox):
        raise ValueError("project_path_outside_sandbox")
    return Path(verified)


# Paths that must keep a raw body stream (custom size caps / signature verify).
# json_body_middleware MUST NOT consume these bodies — they call
# parse_json_object_bytes themselves after a capped read.
RAW_BODY_PATHS = frozenset(
    {
        "/v1/billing/webhook/stripe",
        "/v1/generate",
    }
)


def parse_json_object_bytes(raw: bytes, *, empty_ok: bool = True) -> dict:
    """Single root parser: raw request bytes → JSON object dict.

    Never raises HTTP exceptions — callers map ValueError codes:
      invalid_json | body_must_be_object

    Empty / whitespace-only body → {} when empty_ok (POST without body is valid
    for rotate_key, diagnose, portal, etc.).
    """
    import json

    if raw is None or not raw.strip():
        if empty_ok:
            return {}
        raise ValueError("invalid_json")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid_json") from exc
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc
    if body is None:
        if empty_ok:
            return {}
        raise ValueError("invalid_json")
    if not isinstance(body, dict):
        raise ValueError("body_must_be_object")
    return body


async def read_capped_body(request, *, max_bytes: int) -> bytes:
    """Read request body with a hard byte cap. Raises ValueError with stable codes."""
    cl = request.headers.get("Content-Length")
    if cl is not None:
        try:
            n = int(cl)
        except ValueError as exc:
            raise ValueError("invalid_content_length") from exc
        if n < 0 or n > max_bytes:
            raise ValueError("payload_too_large")
    try:
        raw = await request.content.read(max_bytes + 1)
    except Exception as exc:
        raise ValueError("body_read_failed") from exc
    if len(raw) > max_bytes:
        raise ValueError("payload_too_large")
    return raw


async def safe_json_body(
    request,
    *,
    required: bool = True,
    max_bytes: int = 65536,
) -> dict:
    """Parse JSON body safely via the single root parser.

    Root contract:
    - Prefer request['json_body'] when json_body_middleware already parsed.
    - Otherwise read capped bytes + parse_json_object_bytes (never request.json()).
    - Invalid / non-object JSON → HTTP 400 with stable error code.
    - Empty body → {} (required flag only rejects missing *fields* at the route).
    """
    from aiohttp import web

    def _http_for(code: str):
        if code == "payload_too_large":
            return web.HTTPRequestEntityTooLarge(
                max_size=max_bytes,
                actual_size=max_bytes + 1,
                text='{"error":"payload_too_large"}',
                content_type="application/json",
            )
        return web.HTTPBadRequest(
            text=f'{{"error":"{code}"}}',
            content_type="application/json",
        )

    if request.get("json_body_parsed"):
        body = request.get("json_body")
        if isinstance(body, dict):
            return body
        raise _http_for("invalid_json")

    try:
        raw = await read_capped_body(request, max_bytes=max_bytes)
        body = parse_json_object_bytes(raw, empty_ok=True)
    except ValueError as exc:
        raise _http_for(str(exc) or "invalid_json") from exc

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
