"""Workspace filesystem tools for the free Cline agent.

All paths are relative to work_dir and enforced via safe_fs — no escapes.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from lumen.engine.services.safe_fs import (
    UnsafePathError,
    safe_resolve_under,
    safe_write_text,
)

logger = logging.getLogger(__name__)

_MAX_READ = 120_000
_MAX_TREE_ENTRIES = 200


def _root(work_dir: str | Path) -> Path:
    return Path(work_dir).resolve()


def list_dir(work_dir: str, path: str = ".") -> dict[str, Any]:
    try:
        root = _root(work_dir)
        rel = (path or ".").strip() or "."
        if rel in {".", ""}:
            target = root
        else:
            target = safe_resolve_under(root, rel)
        if not target.exists():
            return {"ok": False, "error": "not_found", "path": rel}
        if not target.is_dir():
            return {"ok": False, "error": "not_a_directory", "path": rel}
        entries: list[dict[str, Any]] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name)[:150]:
            try:
                entries.append(
                    {
                        "name": child.name,
                        "type": "dir" if child.is_dir() else "file",
                        "size": child.stat().st_size if child.is_file() else None,
                    }
                )
            except OSError:
                continue
        return {"ok": True, "path": rel, "entries": entries}
    except UnsafePathError as exc:
        return {"ok": False, "error": f"unsafe:{exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def read_file(work_dir: str, path: str) -> dict[str, Any]:
    try:
        root = _root(work_dir)
        target = safe_resolve_under(root, path)
        if not target.exists() or not target.is_file():
            return {"ok": False, "error": "not_found", "path": path}
        data = target.read_bytes()
        if len(data) > _MAX_READ:
            text = data[:_MAX_READ].decode("utf-8", errors="replace")
            return {
                "ok": True,
                "path": path,
                "content": text,
                "truncated": True,
                "size": len(data),
            }
        return {
            "ok": True,
            "path": path,
            "content": data.decode("utf-8", errors="replace"),
            "truncated": False,
            "size": len(data),
        }
    except UnsafePathError as exc:
        return {"ok": False, "error": f"unsafe:{exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def write_file(work_dir: str, path: str, content: str) -> dict[str, Any]:
    try:
        root = _root(work_dir)
        root.mkdir(parents=True, exist_ok=True)
        target = safe_write_text(root, path, content if isinstance(content, str) else str(content))
        rel = target.relative_to(root).as_posix()
        return {"ok": True, "path": rel, "bytes": target.stat().st_size}
    except UnsafePathError as exc:
        return {"ok": False, "error": f"unsafe:{exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def edit_file(
    work_dir: str,
    path: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
) -> dict[str, Any]:
    try:
        root = _root(work_dir)
        target = safe_resolve_under(root, path)
        if not target.exists() or not target.is_file():
            return {"ok": False, "error": "not_found", "path": path}
        text = target.read_text(encoding="utf-8", errors="replace")
        if old_string not in text:
            return {"ok": False, "error": "old_string_not_found", "path": path}
        if replace_all:
            updated = text.replace(old_string, new_string)
            count = text.count(old_string)
        else:
            updated = text.replace(old_string, new_string, 1)
            count = 1
        preflight = None
        try:
            from lumen.engine.services.code_intelligence.preflight import analyze_edit_preflight
            preflight = analyze_edit_preflight(
                work_dir,
                path,
                old_string=old_string,
                new_string=new_string,
            )
        except Exception as _pf_exc:
            preflight = {"ok": False, "error": type(_pf_exc).__name__}
        safe_write_text(root, path, updated)
        out: dict[str, Any] = {"ok": True, "path": path, "replacements": count}
        if isinstance(preflight, dict):
            out["preflight"] = {
                "risk": preflight.get("risk"),
                "impact_score": preflight.get("impact_score"),
                "impacted_files": (preflight.get("impacted_files_union") or [])[:20],
                "symbol_hints": preflight.get("symbol_hints") or [],
                "jedi_refs": (preflight.get("jedi") or {}).get("refs"),
                "engine": preflight.get("engine"),
            }
        return out
    except UnsafePathError as exc:
        return {"ok": False, "error": f"unsafe:{exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def tree(work_dir: str, path: str = ".", max_depth: int = 4) -> dict[str, Any]:
    try:
        root = _root(work_dir)
        rel = (path or ".").strip() or "."
        start = root if rel in {".", ""} else safe_resolve_under(root, rel)
        if not start.exists():
            return {"ok": False, "error": "not_found", "path": rel}
        lines: list[str] = []
        count = 0

        def walk(p: Path, prefix: str, depth: int) -> None:
            nonlocal count
            if count >= _MAX_TREE_ENTRIES or depth > max_depth:
                return
            try:
                children = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            except OSError:
                return
            for i, child in enumerate(children):
                if count >= _MAX_TREE_ENTRIES:
                    lines.append(prefix + "...")
                    return
                last = i == len(children) - 1
                branch = "└── " if last else "├── "
                lines.append(f"{prefix}{branch}{child.name}{'/' if child.is_dir() else ''}")
                count += 1
                if child.is_dir():
                    walk(child, prefix + ("    " if last else "│   "), depth + 1)

        lines.append(rel if rel != "." else ".")
        if start.is_dir():
            walk(start, "", 1)
        return {"ok": True, "path": rel, "tree": "\n".join(lines), "entries": count}
    except UnsafePathError as exc:
        return {"ok": False, "error": f"unsafe:{exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}




def run_shell(work_dir: str, command: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Run a shell command inside work_dir only when CLINE_ALLOW_SHELL=1."""
    flag = (os.getenv("CLINE_ALLOW_SHELL") or "0").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return {"ok": False, "error": "shell_disabled_set_CLINE_ALLOW_SHELL=1"}
    cmd = (command or "").strip()
    if not cmd:
        return {"ok": False, "error": "empty_command"}
    # block obvious destructive absolute system paths
    banned = ("rm -rf /", "mkfs", ":(){", "shutdown", "reboot")
    low = cmd.lower()
    if any(b in low for b in banned):
        return {"ok": False, "error": "command_blocked_policy"}
    root = _root(work_dir)
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=max(5.0, min(120.0, float(timeout))),
            env={**os.environ, "PWD": str(root)},
        )
        out = (proc.stdout or "")[-8000:]
        err = (proc.stderr or "")[-4000:]
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": out,
            "stderr": err,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}

def _coerce_rel_path(work_dir: str, path: str) -> str:
    """Coerce absolute/escaped paths into workspace-relative paths."""
    raw = (path or ".").strip() or "."
    if raw in {".", "./", ""}:
        return "."
    try:
        p = Path(raw)
        if p.is_absolute():
            root = Path(work_dir).resolve()
            try:
                return p.resolve().relative_to(root).as_posix() or "."
            except Exception:
                # bare absolute outside workspace → use name only if under cwd-like
                return p.name or "."
    except Exception:
        pass
    return raw.lstrip("/") or "."


def run_tool(work_dir: str, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch FS tool by name."""
    args = dict(args or {})
    if "path" in args and args.get("path") is not None:
        args["path"] = _coerce_rel_path(work_dir, str(args.get("path") or "."))
    if name == "list_dir":
        return list_dir(work_dir, str(args.get("path") or "."))
    if name == "read_file":
        return read_file(work_dir, str(args.get("path") or ""))
    if name == "write_file":
        return write_file(
            work_dir,
            str(args.get("path") or ""),
            str(args.get("content") if args.get("content") is not None else ""),
        )
    if name in {"edit_file", "apply_patch", "search_replace"}:
        return edit_file(
            work_dir,
            str(args.get("path") or ""),
            str(args.get("old_string") or ""),
            str(args.get("new_string") if args.get("new_string") is not None else ""),
            replace_all=bool(args.get("replace_all")),
        )
    if name == "tree":
        try:
            depth = int(args.get("max_depth") or 4)
        except (TypeError, ValueError):
            depth = 4
        return tree(work_dir, str(args.get("path") or "."), max_depth=depth)
    if name == "run_shell":
        try:
            t = float(args.get("timeout") or 30)
        except (TypeError, ValueError):
            t = 30.0
        return run_shell(work_dir, str(args.get("command") or ""), timeout=t)
    if name == "finish":
        return {
            "ok": True,
            "finished": True,
            "summary": str(args.get("summary") or args.get("message") or ""),
        }
    return {"ok": False, "error": f"unknown_tool:{name}"}


__all__ = [
    "edit_file",
    "list_dir",
    "read_file",
    "run_tool",
    "tree",
    "write_file",
]
