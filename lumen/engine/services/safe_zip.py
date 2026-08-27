"""TOCTOU-hardened ZIP packaging for project deliverables.

Rules:
- Never follow symlinks (dirs or files).
- Open files with O_NOFOLLOW; read bytes then ZipFile.writestr.
- Refuse paths that escape project root after resolve.
- Skip secrets and junk by name.
"""
from __future__ import annotations

import logging
import os
import stat
import zipfile
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_DEFAULT_EXCLUDED_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "node_modules",
})
_DEFAULT_EXCLUDED_NAMES = frozenset({
    ".env", ".env.local", ".env.production", "secrets.json",
    ".tbe_bot_token", ".cancel",
})


def _read_nofollow(path: Path, *, max_bytes: int) -> bytes | None:
    try:
        st = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    if st.st_size > max_bytes:
        logger.warning("safe_zip skip oversized %s (%s)", path, st.st_size)
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
        try:
            return os.read(fd, int(st.st_size) + 1)
        finally:
            os.close(fd)
    except OSError as exc:
        logger.warning("safe_zip open failed %s: %s", path, exc)
        return None


def write_project_zip(
    project_path: str | Path,
    zip_path: str | Path | None = None,
    *,
    max_file_bytes: int = 8 * 1024 * 1024,
    excluded_dirs: Iterable[str] | None = None,
    excluded_names: Iterable[str] | None = None,
) -> Path | None:
    """Package project_path into a zip. Returns zip path or None on failure."""
    root = Path(project_path).resolve()
    if not root.is_dir():
        return None
    dest = Path(zip_path) if zip_path else root.parent / f"{root.name}.zip"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.exception("safe_zip mkdir failed")
        return None
    skip_dirs = set(excluded_dirs) if excluded_dirs is not None else set(_DEFAULT_EXCLUDED_DIRS)
    skip_names = set(excluded_names) if excluded_names is not None else set(_DEFAULT_EXCLUDED_NAMES)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                # prune symlinked dirs and excluded names
                keep = []
                for d in dirnames:
                    p = Path(dirpath) / d
                    if d in skip_dirs or d.startswith("."):
                        continue
                    try:
                        if p.is_symlink():
                            continue
                    except OSError:
                        continue
                    keep.append(d)
                dirnames[:] = keep
                for name in filenames:
                    if name in skip_names or name.endswith((".pyc", ".pyo", ".log")):
                        continue
                    full = Path(dirpath) / name
                    data = _read_nofollow(full, max_bytes=max_file_bytes)
                    if data is None:
                        continue
                    try:
                        resolved = full.resolve()
                        arc = resolved.relative_to(root)
                    except ValueError:
                        logger.warning("safe_zip skip outside root: %s", full)
                        continue
                    zf.writestr(arc.as_posix(), data)
        os.replace(tmp, dest)
        return dest
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        logger.exception("safe_zip failed for %s", root)
        return None


class UnsafeZipError(ValueError):
    """Zip content rejected for security policy."""


def safe_extract_zip(
    zip_path: str | Path,
    dest_dir: str | Path,
    *,
    max_files: int = 50_000,
    max_total_bytes: int = 512 * 1024 * 1024,
) -> Path:
    """Extract zip under dest_dir with Zip-Slip protection.

    Rejects absolute paths, '..' components, and symlink members.
    """
    zpath = Path(zip_path)
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    total = 0
    n = 0
    with zipfile.ZipFile(zpath, "r") as zf:
        for info in zf.infolist():
            name = info.filename or ""
            if not name:
                continue
            if name.endswith("/"):
                rel = name.rstrip("/")
                if not rel:
                    continue
                if name.startswith("/") or ".." in Path(rel).parts:
                    raise UnsafeZipError(f"zip_slip_dir:{name}")
                (dest / rel).mkdir(parents=True, exist_ok=True)
                continue
            if name.startswith("/") or name.startswith("\\"):
                raise UnsafeZipError(f"zip_slip_abs:{name}")
            parts = Path(name).parts
            if ".." in parts:
                raise UnsafeZipError(f"zip_slip:{name}")
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise UnsafeZipError(f"zip_symlink_forbidden:{name}")
            n += 1
            if n > max_files:
                raise UnsafeZipError("zip_too_many_files")
            target = (dest / name).resolve()
            try:
                target.relative_to(dest)
            except ValueError as exc:
                raise UnsafeZipError(f"zip_slip_escape:{name}") from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_total_bytes:
                        raise UnsafeZipError("zip_too_large")
                    out.write(chunk)
    return dest
