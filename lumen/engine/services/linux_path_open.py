"""Linux openat2 path resolution — kernel-enforced anti-TOCTOU.

Uses the openat2(2) syscall (Linux 5.6+) with:
  RESOLVE_BENEATH     — path must stay under the dirfd root
  RESOLVE_NO_SYMLINKS — refuse any symlink in the walk
  RESOLVE_NO_MAGICLINKS — refuse /proc/self/fd style magic links

This is the authoritative containment primitive for sandbox paths.
pathlib.is_symlink() is never used as a security boundary.

Fallback on non-Linux / old kernels: O_DIRECTORY|O_NOFOLLOW on the final
component only (strict, fail-closed for security-sensitive callers that
require openat2 via require_openat2=True).
"""
from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final


# open_how.resolve flags (uapi/linux/openat2.h)
RESOLVE_NO_XDEV: Final[int] = 0x01
RESOLVE_NO_MAGICLINKS: Final[int] = 0x02
RESOLVE_NO_SYMLINKS: Final[int] = 0x04
RESOLVE_BENEATH: Final[int] = 0x08
RESOLVE_IN_ROOT: Final[int] = 0x10

# Default harden mask for sandbox opens
_DEFAULT_RESOLVE: Final[int] = (
    RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS
)

# syscall numbers
_NR_OPENAT2_X86_64: Final[int] = 437
_NR_OPENAT2_AARCH64: Final[int] = 437  # same on most arches post-5.6


class OpenHow(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint64),
        ("mode", ctypes.c_uint64),
        ("resolve", ctypes.c_uint64),
    ]


class PathOpenError(OSError):
    """Path open refused by kernel policy or unavailable primitive."""


def _libc() -> ctypes.CDLL:
    lib = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    return lib


def openat2_available() -> bool:
    if sys.platform != "linux":
        return False
    try:
        # Probe: openat2 on AT_FDCWD with empty path must fail; ENOSYS means absent
        lib = _libc()
        how = OpenHow(flags=os.O_RDONLY, mode=0, resolve=RESOLVE_NO_SYMLINKS)
        nr = _NR_OPENAT2_X86_64
        AT_FDCWD = -100
        lib.syscall.restype = ctypes.c_long
        lib.syscall.argtypes = [
            ctypes.c_long,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.POINTER(OpenHow),
            ctypes.c_size_t,
        ]
        rc = lib.syscall(nr, AT_FDCWD, b"", ctypes.byref(how), ctypes.sizeof(how))
        if rc >= 0:
            os.close(rc)
            return True
        err = ctypes.get_errno()
        # ENOSYS = not supported; other errors mean syscall exists
        return err != getattr(errno, "ENOSYS", 38)
    except Exception:
        return False


_OPENAT2_OK: bool | None = None


def _has_openat2() -> bool:
    global _OPENAT2_OK
    if _OPENAT2_OK is None:
        _OPENAT2_OK = openat2_available()
    return _OPENAT2_OK


def openat2(
    dirfd: int,
    path: str | bytes,
    *,
    flags: int = os.O_RDONLY,
    mode: int = 0,
    resolve: int = _DEFAULT_RESOLVE,
) -> int:
    """Call openat2(2). Returns fd. Raises PathOpenError on refusal/absence."""
    if sys.platform != "linux":
        raise PathOpenError(errno.ENOSYS, "openat2 requires Linux")
    lib = _libc()
    how = OpenHow(flags=ctypes.c_uint64(flags), mode=ctypes.c_uint64(mode), resolve=ctypes.c_uint64(resolve))
    if isinstance(path, str):
        path_b = os.fsencode(path)
    else:
        path_b = path
    lib.syscall.restype = ctypes.c_long
    lib.syscall.argtypes = [
        ctypes.c_long,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(OpenHow),
        ctypes.c_size_t,
    ]
    rc = lib.syscall(
        _NR_OPENAT2_X86_64,
        int(dirfd),
        path_b,
        ctypes.byref(how),
        ctypes.sizeof(how),
    )
    if rc < 0:
        err = ctypes.get_errno()
        raise PathOpenError(err, os.strerror(err))
    return int(rc)


@dataclass(frozen=True)
class OpenedPath:
    """Result of a contained open: fd + real path string for callers that need Path."""
    fd: int
    realpath: str

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


def _lexical_rel_under(root_p: Path, target: Path) -> str:
    """Return relative path under root **without following symlinks**.

    Following (Path.resolve) before openat2 would erase symlink components and
    defeat RESOLVE_NO_SYMLINKS. We only allow lexical containment.
    """
    root_s = os.path.abspath(str(root_p))
    # abspath does not resolve symlinks in intermediate components on Linux
    # the same way realpath does; still normalize .. carefully.
    if target.is_absolute():
        tgt_s = os.path.abspath(str(target))
    else:
        tgt_s = os.path.abspath(str(root_p / target))
    root_prefix = root_s if root_s.endswith(os.sep) else root_s + os.sep
    if tgt_s == root_s:
        return ""
    if not tgt_s.startswith(root_prefix):
        raise PathOpenError(errno.EPERM, "path_outside_root")
    rel = tgt_s[len(root_prefix):]
    # Refuse any .. that survived
    parts = [p for p in rel.replace("\\", "/").split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise PathOpenError(errno.EPERM, "path_traversal")
    return "/".join(parts)


def open_beneath(
    root: str | Path,
    relative_or_abs: str | Path,
    *,
    directory: bool = True,
    flags: int | None = None,
    resolve: int = _DEFAULT_RESOLVE,
    require_openat2: bool = True,
) -> OpenedPath:
    """Open path so it must remain under *root* with no symlink traversal.

    Preferred path: open root as dirfd, then openat2(relative, RESOLVE_BENEATH|…).
    Relative form is computed lexically (no symlink follow) so the kernel still
    sees symlink components and RESOLVE_NO_SYMLINKS can refuse them.
    """
    root_p = Path(os.path.abspath(str(root)))
    target = Path(relative_or_abs)
    rel_s = _lexical_rel_under(root_p, target)

    if ".." in Path(rel_s).parts:
        raise PathOpenError(errno.EPERM, "path_traversal")

    base_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if directory:
        base_flags |= getattr(os, "O_DIRECTORY", 0)
    if flags is not None:
        base_flags = flags

    # Open root dirfd without following final symlink when possible
    root_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        root_fd = os.open(str(root_p), root_flags)
    except OSError as exc:
        # Root itself must be a real directory
        raise PathOpenError(exc.errno, f"root_open_failed:{exc.strerror}") from exc

    try:
        # require_openat2=False is rejected unless explicit weak-path emergency (dev only).
        allow_weak = (
            not require_openat2
            and (os.environ.get("TBE_ALLOW_WEAK_PATH_OPEN") or "").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        if not _has_openat2() and not allow_weak:
            raise PathOpenError(errno.ENOSYS, "openat2_required_but_unavailable")

        if _has_openat2():
            # Empty relative means open the root itself via dup
            if not rel_s or rel_s == ".":
                # re-verify root with fstat
                st = os.fstat(root_fd)
                if not stat.S_ISDIR(st.st_mode):
                    raise PathOpenError(errno.ENOTDIR, "root_not_directory")
                # dup so caller can close independently
                fd = os.dup(root_fd)
                return OpenedPath(fd=fd, realpath=str(root_p))
            fd = openat2(
                root_fd,
                rel_s,
                flags=base_flags | getattr(os, "O_NOFOLLOW", 0),
                mode=0,
                resolve=resolve,
            )
            # Derive realpath via readlink /proc/self/fd (does not re-walk user path)
            try:
                real = os.readlink(f"/proc/self/fd/{fd}")
            except OSError:
                real = str((root_p / rel_s).resolve(strict=False))
            return OpenedPath(fd=fd, realpath=real)

        # ROOT FIX: never use O_NOFOLLOW-only open on a full path — intermediate
        # symlinks can escape the sandbox. openat2(RESOLVE_BENEATH|NO_SYMLINKS) only.
        raise PathOpenError(errno.ENOSYS, "openat2_required_but_unavailable")
    finally:
        try:
            os.close(root_fd)
        except OSError:
            pass


def verify_dir_beneath(root: str | Path, path: str | Path, *, require_openat2: bool = True) -> Path:
    """Open-and-verify directory under root; close fd; return real Path.

    Security-sensitive API for validate_*_project_path.
    """
    opened = open_beneath(root, path, directory=True, require_openat2=require_openat2)
    try:
        st = os.fstat(opened.fd)
        if not stat.S_ISDIR(st.st_mode):
            raise PathOpenError(errno.ENOTDIR, "not_a_directory")
        real = Path(opened.realpath)
        root_real = Path(os.path.realpath(str(root)))
        try:
            real.resolve().relative_to(root_real)
        except ValueError as exc:
            raise PathOpenError(errno.EPERM, "resolved_outside_root") from exc
        return real
    finally:
        opened.close()


__all__ = [
    "PathOpenError",
    "OpenedPath",
    "openat2",
    "openat2_available",
    "open_beneath",
    "verify_dir_beneath",
    "RESOLVE_BENEATH",
    "RESOLVE_NO_SYMLINKS",
    "RESOLVE_NO_MAGICLINKS",
    "RESOLVE_NO_XDEV",
]
