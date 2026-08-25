"""Safe filesystem writes for generated projects.

Foundation rules:
1. Every write target must resolve *inside* a declared project root.
2. Project roots themselves must resolve *inside* OUTPUT_DIR (unless explicit temp allow).
3. No absolute paths, no "..", no symlink escapes, no oversized files.
"""
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


import os
import re
from pathlib import Path

_SAFE_REL = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_FILE_BYTES = int(os.getenv("TBE_MAX_GENERATED_FILE_BYTES") or str(2 * 1024 * 1024))


class UnsafePathError(ValueError):
    """Raised when a write target would escape the allowed root."""


def output_dir() -> Path:
    return Path(os.getenv("OUTPUT_DIR") or _cm_default_output_dir()).resolve()


def enforce_under_output_dir(path: Path | str, *, allow_temp_prefix: str = "spec_bot_") -> Path:
    """Refuse any generation/workdir outside OUTPUT_DIR.

    Exception: ephemeral dirs created via mkdtemp(prefix=allow_temp_prefix) under
    the system temp dir, only when TBE_ALLOW_TEMP_WORKDIR=1 (local unit tests).
    """
    p = Path(path).resolve()
    out = output_dir()
    try:
        p.relative_to(out)
        return p
    except ValueError:
        pass
    allow_temp = (os.getenv("TBE_ALLOW_TEMP_WORKDIR") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if allow_temp and allow_temp_prefix and allow_temp_prefix in p.name:
        # still must not be clearly sensitive system paths
        forbidden = ("/etc", "/usr", "/bin", "/sbin", "/boot", "/root", "/home")
        s = str(p)
        if any(s == f or s.startswith(f + "/") for f in forbidden):
            raise UnsafePathError("workdir_forbidden_system_path")
        return p
    raise UnsafePathError(f"workdir_outside_output_dir:{p}")


def safe_ident(name: str) -> str:
    """Accept only Python identifiers (service module names, etc.)."""
    n = (name or "").strip()
    if not _SAFE_IDENT.fullmatch(n):
        raise UnsafePathError(f"invalid_identifier:{name!r}")
    return n


def safe_resolve_under(root: Path, rel: str) -> Path:
    """Return resolved path for *rel* only if it stays under *root*."""
    root = Path(root).resolve()
    raw = (rel or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("~"):
        raise UnsafePathError("absolute_or_empty_path")
    if not _SAFE_REL.fullmatch(raw):
        raise UnsafePathError("path_chars_rejected")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts) or not parts:
        raise UnsafePathError("path_traversal_rejected")

    candidate = root.joinpath(*parts)
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (ValueError, OSError) as exc:
        raise UnsafePathError("path_outside_root") from exc

    cur = root
    for part in parts:
        cur = cur / part
        try:
            if cur.exists() and cur.is_symlink():
                target = cur.resolve()
                target.relative_to(root)
        except (ValueError, OSError) as exc:
            raise UnsafePathError("symlink_escape") from exc
    return resolved


def safe_write_text(
    root: Path,
    rel: str,
    content: str,
    *,
    max_bytes: int | None = None,
) -> Path:
    """Write UTF-8 text to root/rel with containment + size limits."""
    limit = int(max_bytes if max_bytes is not None else _MAX_FILE_BYTES)
    data = content if isinstance(content, str) else str(content)
    if len(data.encode("utf-8")) > limit:
        raise UnsafePathError("file_too_large")
    target = safe_resolve_under(root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.resolve(strict=False).relative_to(Path(root).resolve())
    except (ValueError, OSError) as exc:
        raise UnsafePathError("path_outside_root_after_mkdir") from exc
    # Use-time TOCTOU: refuse if any component became a symlink since resolve
    assert_no_symlinks_in_path(target, root=root)
    # Write without following symlinks (O_NOFOLLOW) when the file already exists
    import os
    flags = getattr(os, "O_WRONLY", 1) | getattr(os, "O_CREAT", 64) | getattr(os, "O_TRUNC", 512)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    raw = data.encode("utf-8")
    try:
        fd = os.open(str(target), flags | nofollow, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
    except OSError:
        # O_NOFOLLOW may fail on some FS if file missing races — re-check then write
        assert_no_symlinks_in_path(target, root=root)
        if target.is_symlink():
            raise UnsafePathError("write_target_is_symlink")
        target.write_bytes(raw)
    return target


def safe_write_under_root(root: Path, abs_or_rel: Path, content: str) -> Path:
    """Write to a path that must already resolve under root (for repair helpers)."""
    root = Path(root).resolve()
    target = Path(abs_or_rel).resolve()
    try:
        rel = target.relative_to(root).as_posix()
    except ValueError as exc:
        raise UnsafePathError("path_outside_root") from exc
    return safe_write_text(root, rel, content)


def assert_no_symlinks_in_path(path: Path | str, *, root: Path | str | None = None) -> Path:
    """Re-check every component is not a symlink (TOCTOU defense at use time).

    Call immediately before open/read/write/exec — not only at initial validation.
    """
    p = Path(path).resolve(strict=False)
    if root is not None:
        r = Path(root).resolve()
        try:
            p.relative_to(r)
        except ValueError as exc:
            raise UnsafePathError("path_outside_root") from exc
        base = r
        rel_parts = p.relative_to(r).parts
    else:
        base = p.anchor and Path(p.anchor) or Path("/")
        # walk from root of path
        rel_parts = p.parts[1:] if p.is_absolute() else p.parts
        base = Path(p.parts[0]) if p.is_absolute() else Path(".")

    cur = Path(root).resolve() if root is not None else (Path(p.anchor) if p.is_absolute() else Path(".").resolve())
    if root is not None:
        cur = Path(root).resolve()
        for part in Path(path).resolve().relative_to(cur).parts:
            cur = cur / part
            try:
                if cur.is_symlink():
                    raise UnsafePathError(f"symlink_component_forbidden:{cur}")
            except OSError as exc:
                raise UnsafePathError("symlink_stat_failed") from exc
    else:
        # absolute walk
        cur = Path(p.anchor) if p.is_absolute() else Path(".")
        parts = p.parts[1:] if p.is_absolute() else p.parts
        for part in parts:
            cur = cur / part
            try:
                if cur.exists() and cur.is_symlink():
                    raise UnsafePathError(f"symlink_component_forbidden:{cur}")
            except OSError as exc:
                raise UnsafePathError("symlink_stat_failed") from exc
    # final resolve must still be under root if given
    final = p.resolve(strict=False)
    if root is not None:
        try:
            final.relative_to(Path(root).resolve())
        except ValueError as exc:
            raise UnsafePathError("resolved_outside_root") from exc
    if final.is_symlink():
        raise UnsafePathError("final_path_is_symlink")
    return final


def safe_open_under(root: Path | str, rel: str, mode: str = "r", **kwargs):
    """Open a file under root with symlink rejection at open time (read and write)."""
    import os
    path = safe_resolve_under(Path(root), rel)
    path = assert_no_symlinks_in_path(path, root=root)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    # Map common modes to flags + O_NOFOLLOW
    if "w" in mode or "a" in mode or "x" in mode or "+" in mode:
        flags = getattr(os, "O_RDWR", 2) if "+" in mode else getattr(os, "O_WRONLY", 1)
        if "w" in mode:
            flags |= getattr(os, "O_CREAT", 64) | getattr(os, "O_TRUNC", 512)
        if "a" in mode:
            flags |= getattr(os, "O_CREAT", 64) | getattr(os, "O_APPEND", 1024)
        if "x" in mode:
            flags |= getattr(os, "O_CREAT", 64) | getattr(os, "O_EXCL", 128)
        try:
            fd = os.open(str(path), flags | nofollow, 0o600)
            return open(fd, mode, **kwargs)
        except OSError:
            assert_no_symlinks_in_path(path, root=root)
            if path.is_symlink():
                raise UnsafePathError("open_target_is_symlink")
            return open(path, mode, **kwargs)
    # read-only
    flags = getattr(os, "O_RDONLY", 0) | nofollow
    try:
        fd = os.open(str(path), flags)
        return open(fd, mode, **kwargs)
    except OSError:
        assert_no_symlinks_in_path(path, root=root)
        return open(path, mode, **kwargs)

