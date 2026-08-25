"""Safe filesystem writes for generated projects.

Foundation rules:
1. Every write target must resolve *inside* a declared project root.
2. Project roots themselves must resolve *inside* OUTPUT_DIR (unless explicit temp allow).
3. No absolute paths, no "..", no symlink escapes, no oversized files.
4. TOCTOU: never trust a prior is_symlink() check alone — open with O_NOFOLLOW
   (and O_DIRECTORY for dirs) so the kernel refuses symlink substitution at use time.
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
import stat
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


def _lstat_is_symlink(path: Path) -> bool:
    """True if path is a symlink — uses lstat (never follows)."""
    try:
        return stat.S_ISLNK(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise UnsafePathError("lstat_failed") from exc


def assert_no_symlinks_in_path(path: Path | str, *, root: Path | str | None = None) -> Path:
    """Re-check every component is not a symlink via lstat (never follows).

    Call immediately before open/read/write/exec — not only at initial validation.
    """
    raw = Path(path)
    if root is not None:
        r = Path(root).resolve(strict=False)
        # Walk components under root using lstat only
        try:
            # Prefer relative walk from root when path is under root after resolve
            candidate = raw if raw.is_absolute() else (r / raw)
            # Build component chain without following
            parts: list[str] = []
            cur = candidate
            # Normalize string parts without resolve-follow
            s = str(candidate)
            # Use resolve(strict=False) only after component lstat checks
            walk_base = r
            rel_try = None
            try:
                rel_try = Path(os.path.realpath(str(candidate))).relative_to(
                    Path(os.path.realpath(str(r)))
                )
            except Exception:
                rel_try = None
            if rel_try is not None:
                cur = r
                for part in rel_try.parts:
                    cur = cur / part
                    if _lstat_is_symlink(cur):
                        raise UnsafePathError(f"symlink_component_forbidden:{cur}")
            else:
                # Absolute walk with lstat
                cur = Path(candidate.anchor) if candidate.is_absolute() else Path(".")
                parts = candidate.parts[1:] if candidate.is_absolute() else candidate.parts
                for part in parts:
                    cur = cur / part
                    if _lstat_is_symlink(cur):
                        raise UnsafePathError(f"symlink_component_forbidden:{cur}")
        except UnsafePathError:
            raise
        except OSError as exc:
            raise UnsafePathError("symlink_stat_failed") from exc

        final = Path(os.path.realpath(str(raw)))
        try:
            final.relative_to(Path(os.path.realpath(str(r))))
        except ValueError as exc:
            raise UnsafePathError("resolved_outside_root") from exc
        if _lstat_is_symlink(Path(str(raw))):
            # original path name itself is a symlink
            raise UnsafePathError("final_path_is_symlink")
        if _lstat_is_symlink(final):
            raise UnsafePathError("final_path_is_symlink")
        return final

    # No root: absolute/relative walk with lstat
    p = raw
    cur = Path(p.anchor) if p.is_absolute() else Path(".")
    parts = p.parts[1:] if p.is_absolute() else p.parts
    for part in parts:
        cur = cur / part
        if _lstat_is_symlink(cur):
            raise UnsafePathError(f"symlink_component_forbidden:{cur}")
    final = Path(os.path.realpath(str(p)))
    if _lstat_is_symlink(final) or _lstat_is_symlink(p):
        raise UnsafePathError("final_path_is_symlink")
    return final


def open_directory_nofollow(path: Path | str) -> int:
    """Open a directory fd with O_DIRECTORY|O_NOFOLLOW (atomic anti-TOCTOU).

    Returns an integer fd. Caller must os.close(fd).
    Raises UnsafePathError if path is a symlink or not a directory.
    """
    flags = getattr(os, "O_RDONLY", 0)
    # O_DIRECTORY: fail if not a directory; O_NOFOLLOW: fail if final component is symlink
    o_dir = getattr(os, "O_DIRECTORY", 0)
    o_nofollow = getattr(os, "O_NOFOLLOW", 0)
    o_cloexec = getattr(os, "O_CLOEXEC", 0)
    flags |= o_dir | o_nofollow | o_cloexec
    p = Path(path)
    try:
        fd = os.open(str(p), flags)
    except OSError as exc:
        # Distinguish symlink vs not-a-dir when possible
        if _lstat_is_symlink(p):
            raise UnsafePathError("directory_is_symlink") from exc
        raise UnsafePathError(f"open_directory_failed:{type(exc).__name__}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode):
            os.close(fd)
            raise UnsafePathError("not_a_directory")
        if stat.S_ISLNK(st.st_mode):  # should be unreachable with O_NOFOLLOW
            os.close(fd)
            raise UnsafePathError("directory_is_symlink")
    except UnsafePathError:
        raise
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        raise
    return fd


def verify_directory_nofollow(path: Path | str, *, root: Path | str | None = None) -> Path:
    """Validate path is a real directory under root — prefers openat2.

    Authority order:
      1) linux_path_open.verify_dir_beneath (openat2 RESOLVE_BENEATH|NO_SYMLINKS)
      2) O_DIRECTORY|O_NOFOLLOW fallback
    """
    p = Path(path)
    if root is not None:
        try:
            from lumen.engine.services.linux_path_open import verify_dir_beneath, PathOpenError
            return Path(verify_dir_beneath(root, p, require_openat2=False))
        except Exception as exc:
            # Map to UnsafePathError for callers
            raise UnsafePathError(str(exc) or "path_open_refused") from exc
    assert_no_symlinks_in_path(p)
    fd = open_directory_nofollow(p)
    try:
        real = Path(os.path.realpath(str(p)))
        return real
    finally:
        try:
            os.close(fd)
        except Exception:
            pass


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
        if _lstat_is_symlink(cur):
            raise UnsafePathError("symlink_escape")
    return resolved


def safe_write_text(
    root: Path,
    rel: str,
    content: str,
    *,
    max_bytes: int | None = None,
) -> Path:
    """Write UTF-8 text to root/rel with containment + size limits + O_NOFOLLOW."""
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
    assert_no_symlinks_in_path(target, root=root)
    flags = getattr(os, "O_WRONLY", 1) | getattr(os, "O_CREAT", 64) | getattr(os, "O_TRUNC", 512)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    raw = data.encode("utf-8")
    try:
        fd = os.open(str(target), flags | nofollow, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
    except OSError as exc:
        # Never fall back to following open — re-check then retry O_NOFOLLOW only
        assert_no_symlinks_in_path(target, root=root)
        if _lstat_is_symlink(target):
            raise UnsafePathError("write_target_is_symlink") from exc
        # File may not exist yet; O_NOFOLLOW on create is fine on Linux for new files
        try:
            fd = os.open(str(target), flags | nofollow, 0o600)
            try:
                os.write(fd, raw)
            finally:
                os.close(fd)
        except OSError as exc2:
            raise UnsafePathError(f"write_failed:{type(exc2).__name__}") from exc2
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


def safe_open_under(root: Path | str, rel: str, mode: str = "r", **kwargs):
    """Open a file under root with O_NOFOLLOW at open time — never follow symlinks."""
    path = safe_resolve_under(Path(root), rel)
    path = assert_no_symlinks_in_path(path, root=root)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
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
        except OSError as exc:
            if _lstat_is_symlink(path):
                raise UnsafePathError("open_target_is_symlink") from exc
            raise UnsafePathError(f"open_failed:{type(exc).__name__}") from exc
    flags = getattr(os, "O_RDONLY", 0) | nofollow
    try:
        fd = os.open(str(path), flags)
        return open(fd, mode, **kwargs)
    except OSError as exc:
        if _lstat_is_symlink(path):
            raise UnsafePathError("open_target_is_symlink") from exc
        raise UnsafePathError(f"open_failed:{type(exc).__name__}") from exc
