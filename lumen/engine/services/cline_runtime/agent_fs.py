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
        text = content if isinstance(content, str) else str(content)
        # Per-user disk quota (best-effort): walk up to users/<id> sandbox root
        try:
            extra = len(text.encode("utf-8"))
            user_root = None
            cur = root
            for _ in range(8):
                if cur.name and (cur.parent / cur.name).exists():
                    # Convention: OUTPUT_DIR/users/<uid>/...
                    if cur.parent.name == "users":
                        user_root = cur
                        break
                if cur.parent == cur:
                    break
                cur = cur.parent
            if user_root is not None:
                from lumen.engine.services.disk_quota import enforce_user_quota
                enforce_user_quota(user_root, extra_bytes=extra)
        except RuntimeError as qexc:
            return {"ok": False, "error": str(qexc)}
        except Exception:
            pass
        target = safe_write_text(root, path, text)
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
        occurrences = text.count(old_string)
        if not replace_all and occurrences > 1:
            return {
                "ok": False,
                "error": "old_string_not_unique",
                "path": path,
                "occurrences": occurrences,
                "hint": "Provide more surrounding context so old_string matches exactly once, or set replace_all=true",
            }
        if replace_all:
            updated = text.replace(old_string, new_string)
            count = occurrences
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
        if isinstance(preflight, dict) and (os.getenv("CODE_INTEL_STRICT") or "").strip().lower() in {"1", "true", "yes"}:
            union = preflight.get("impacted_files_union") or preflight.get("impacted_files") or []
            impact = len(union) if isinstance(union, (list, tuple, set)) else 0
            score = float(preflight.get("impact_score") or 0.0)
            max_files = int(os.getenv("CODE_INTEL_STRICT_MAX_IMPACT") or "25")
            max_score = float(os.getenv("CODE_INTEL_STRICT_MAX_SCORE") or "0.85")
            if impact >= max_files or score >= max_score:
                return {
                    "ok": False,
                    "error": "preflight_blast_radius_too_large",
                    "preflight": {
                        "impact_score": score,
                        "impacted_count": impact,
                        "impacted_files_union": list(union)[:30],
                        "engine": preflight.get("engine"),
                    },
                }

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
        try:
            from lumen.engine.services.code_intelligence.postflight import analyze_edit_postflight
            post = analyze_edit_postflight(work_dir, path)
            out["postflight"] = {
                "ok": post.get("ok"),
                "syntax_ok": post.get("syntax_ok"),
                "syntax_error": post.get("syntax_error"),
                "index_rebuilt": (post.get("index") or {}).get("rebuilt"),
                "engine": post.get("engine"),
            }
            if post.get("syntax_ok") is False:
                out["ok"] = False
                out["error"] = post.get("syntax_error") or "postflight_syntax_error"
        except Exception as _post_exc:
            out["postflight"] = {"ok": False, "error": type(_post_exc).__name__}
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
    """Run a command inside work_dir only when CLINE_ALLOW_SHELL=1.

    Hardened path (default):
      - never uses shell=True (no injection via metacharacters)
      - argv via shlex.split
      - allowlist of base binaries only
      - stripped child env (no API tokens / Telegram secrets)
    """
    import shlex
    import shutil

    flag = (os.getenv("CLINE_ALLOW_SHELL") or "0").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return {"ok": False, "error": "shell_disabled_set_CLINE_ALLOW_SHELL=1"}
    cmd = (command or "").strip()
    if not cmd:
        return {"ok": False, "error": "empty_command"}
    if len(cmd) > 2000:
        return {"ok": False, "error": "command_too_long"}

    banned_substrings = (
        "rm -rf /", "mkfs", ":(){", "shutdown", "reboot", "dd if=",
        "curl ", "wget ", "nc ", "ncat ", "ssh ", "scp ",
        "/etc/passwd", "/etc/shadow", "chmod 777",
        ">(", "<(", "`", "$(",  # process/command substitution
    )
    low = cmd.lower()
    if any(b in low for b in banned_substrings):
        return {"ok": False, "error": "command_blocked_policy"}

    # Reject shell metacharacters — we never invoke a shell.
    if any(ch in cmd for ch in (";", "|", "&", "\n", "\r", ">", "<")):
        return {"ok": False, "error": "shell_metacharacters_forbidden"}

    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        return {"ok": False, "error": f"command_parse:{exc}"}
    if not argv:
        return {"ok": False, "error": "empty_argv"}

    allowed = {
        "python", "python3", "pip", "pip3", "pytest", "ls", "cat", "head",
        "tail", "wc", "echo", "true", "false", "pwd", "which", "test",
        "mkdir", "cp", "mv", "rm", "touch", "find", "grep", "sed", "awk",
        "git", "node", "npm", "npx",
    }
    # Allow env override of extra binaries (comma-separated)
    extra = (os.getenv("CLINE_SHELL_ALLOW_BINARIES") or "").strip()
    if extra:
        allowed |= {x.strip() for x in extra.split(",") if x.strip()}

    binary = Path(argv[0]).name
    if binary not in allowed:
        return {"ok": False, "error": f"binary_not_allowlisted:{binary}"}

    resolved = shutil.which(argv[0]) if "/" not in argv[0] else (
        argv[0] if Path(argv[0]).is_file() else None
    )
    if not resolved:
        return {"ok": False, "error": f"binary_not_found:{argv[0]}"}
    argv[0] = resolved

    # rm: only allow relative paths under work_dir (no leading /)
    if binary == "rm":
        for a in argv[1:]:
            if a.startswith("-"):
                continue
            if a.startswith("/") or a.startswith("~") or ".." in a.split("/"):
                return {"ok": False, "error": "rm_path_outside_workspace"}

    root = _root(work_dir)
    # Minimal env — drop secrets
    _secret_keys = (
        "TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "GEMINI_API_KEYS", "GROQ_API_KEY",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY", "MONGODB_URI",
        "REDIS_URL", "STRIPE_SECRET_KEY", "API_KEY_PEPPER", "TBE_TOKEN_SECRET",
    )
    child_env = {
        k: v for k, v in os.environ.items()
        if k not in _secret_keys and not k.startswith("GEMINI_API_KEY_")
        and not k.startswith("GROQ_API_KEY_")
    }
    child_env["PWD"] = str(root)
    child_env["HOME"] = str(root)
    child_env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")

    try:
        proc = subprocess.run(
            argv,
            shell=False,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=max(5.0, min(120.0, float(timeout))),
            env=child_env,
        )
        out = (proc.stdout or "")[-8000:]
        err = (proc.stderr or "")[-4000:]
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": out,
            "stderr": err,
            "argv": argv[:8],
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



def grep_codebase(
    work_dir: str,
    pattern: str,
    *,
    glob: str = "**/*",
    max_matches: int = 50,
    case_insensitive: bool = False,
) -> dict[str, Any]:
    """Ripgrep-style content search across the workspace (official agent search tool)."""
    import re as _re
    try:
        root = _root(work_dir)
        if not pattern:
            return {"ok": False, "error": "pattern_required"}
        flags = _re.MULTILINE
        if case_insensitive:
            flags |= _re.IGNORECASE
        try:
            rx = _re.compile(pattern, flags)
        except _re.error as exc:
            return {"ok": False, "error": f"invalid_regex:{exc}"}
        matches: list[dict[str, Any]] = []
        # Prefer system rg when available (same as Cline/OpenCode)
        try:
            cmd = ["rg", "-n", "--no-heading", "-m", str(max(1, min(max_matches, 200)))]
            if case_insensitive:
                cmd.append("-i")
            if glob and glob not in {"**/*", "*"}:
                cmd.extend(["-g", glob])
            cmd.extend(["--", pattern, str(root)])
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if proc.returncode in {0, 1}:
                for line in (proc.stdout or "").splitlines()[: max_matches]:
                    # path:line:content
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        try:
                            rel = Path(parts[0]).resolve().relative_to(root).as_posix()
                        except Exception:
                            rel = parts[0]
                        matches.append({
                            "path": rel,
                            "line": int(parts[1]) if parts[1].isdigit() else 0,
                            "text": parts[2][:300],
                        })
                return {"ok": True, "pattern": pattern, "matches": matches, "engine": "rg", "count": len(matches)}
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.debug("rg failed: %s", exc)

        # Pure-Python fallback
        g = glob if glob else "**/*"
        for fp in sorted(root.glob(g))[:2000]:
            if not fp.is_file():
                continue
            if fp.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".pyc", ".so"}:
                continue
            try:
                if fp.stat().st_size > 400_000:
                    continue
                content = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if rx.search(line):
                    try:
                        rel = fp.relative_to(root).as_posix()
                    except Exception:
                        rel = str(fp)
                    matches.append({"path": rel, "line": i, "text": line[:300]})
                    if len(matches) >= max_matches:
                        return {"ok": True, "pattern": pattern, "matches": matches, "engine": "python", "count": len(matches)}
        return {"ok": True, "pattern": pattern, "matches": matches, "engine": "python", "count": len(matches)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def glob_files(work_dir: str, pattern: str = "**/*", *, max_results: int = 200) -> dict[str, Any]:
    """Find files by glob pattern relative to work_dir."""
    try:
        root = _root(work_dir)
        pat = (pattern or "**/*").strip() or "**/*"
        out: list[str] = []
        for fp in sorted(root.glob(pat))[: max(1, min(max_results, 500))]:
            if not fp.is_file():
                continue
            try:
                out.append(fp.relative_to(root).as_posix())
            except Exception:
                continue
        return {"ok": True, "pattern": pat, "files": out, "count": len(out)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def read_files(work_dir: str, paths: list[str] | None = None, *, max_files: int = 12) -> dict[str, Any]:
    """Batch-read multiple files (Cline-style read_files)."""
    paths = list(paths or [])[: max(1, min(max_files, 20))]
    if not paths:
        return {"ok": False, "error": "paths_required"}
    files: dict[str, Any] = {}
    errors: list[str] = []
    for p in paths:
        r = read_file(work_dir, p)
        if r.get("ok"):
            files[str(p)] = {
                "content": r.get("content"),
                "truncated": r.get("truncated"),
                "size": r.get("size"),
            }
        else:
            errors.append(f"{p}:{r.get('error')}")
    return {"ok": bool(files), "files": files, "errors": errors, "count": len(files)}


def apply_edits(
    work_dir: str,
    edits: list[dict[str, Any]] | None = None,
    *,
    atomic: bool = True,
) -> dict[str, Any]:
    """Multi-file transactional edits.

    Each edit: {path, old_string, new_string, replace_all?}
    On failure with atomic=True, restores original file contents.
    """
    edits = list(edits or [])
    if not edits:
        return {"ok": False, "error": "edits_required"}
    if len(edits) > 40:
        return {"ok": False, "error": "too_many_edits", "max": 40}

    root = _root(work_dir)
    backups: dict[str, str] = {}
    applied: list[dict[str, Any]] = []
    try:
        for i, ed in enumerate(edits):
            path = str(ed.get("path") or "").strip()
            old_s = str(ed.get("old_string") if "old_string" in ed else ed.get("old") or "")
            new_s = str(ed.get("new_string") if "new_string" in ed else ed.get("new") or "")
            replace_all = bool(ed.get("replace_all"))
            if not path:
                raise RuntimeError(f"edit[{i}]:path_required")
            target = safe_resolve_under(root, path)
            if not target.exists():
                raise RuntimeError(f"edit[{i}]:not_found:{path}")
            if path not in backups:
                backups[path] = target.read_text(encoding="utf-8", errors="replace")
            r = edit_file(work_dir, path, old_s, new_s, replace_all=replace_all)
            if not r.get("ok"):
                raise RuntimeError(f"edit[{i}]:{path}:{r.get('error')}")
            applied.append({"path": path, "replacements": r.get("replacements") or r.get("count") or 1})
        return {"ok": True, "applied": applied, "count": len(applied), "atomic": atomic}
    except Exception as exc:
        if atomic and backups:
            for path, content in backups.items():
                try:
                    safe_write_text(root, path, content)
                except Exception:
                    logger.exception("rollback failed for %s", path)
        return {
            "ok": False,
            "error": str(exc)[:500],
            "applied_before_fail": applied,
            "rolled_back": bool(atomic and backups),
        }


def apply_patch(work_dir: str, patch: str) -> dict[str, Any]:
    """Apply a multi-file unified diff or simple *** Update File blocks.

    Supports:
      - Standard unified diffs (--- a/path +++ b/path @@ ...)
      - OpenCode-style lines: *** Update File: path / *** Add File: path
    Atomic: restores all touched files on failure.
    """
    import re as _re
    patch = (patch or "").strip()
    if not patch:
        return {"ok": False, "error": "patch_required"}

    root = _root(work_dir)
    backups: dict[str, str | None] = {}  # None = did not exist
    results: list[dict[str, Any]] = []

    def _backup(rel: str) -> None:
        if rel in backups:
            return
        try:
            target = safe_resolve_under(root, rel)
            if target.exists() and target.is_file():
                backups[rel] = target.read_text(encoding="utf-8", errors="replace")
            else:
                backups[rel] = None
        except Exception:
            backups[rel] = None

    def _rollback() -> None:
        for rel, content in backups.items():
            try:
                if content is None:
                    target = safe_resolve_under(root, rel)
                    if target.exists() and target.is_file():
                        target.unlink()
                else:
                    safe_write_text(root, rel, content)
            except Exception:
                logger.exception("patch rollback failed %s", rel)

    try:
        # *** Add/Update File format (simplified multi-file)
        if "***" in patch and ("Update File" in patch or "Add File" in patch):
            blocks = _re.split(r"(?=^\*\*\* (?:Add|Update|Delete) File:)", patch, flags=_re.M)
            for block in blocks:
                block = block.strip()
                if not block:
                    continue
                m = _re.match(r"\*\*\* (Add|Update|Delete) File:\s*(.+)$", block, flags=_re.M)
                if not m:
                    continue
                kind, rel = m.group(1), m.group(2).strip()
                body = block[m.end():].lstrip("\n")
                _backup(rel)
                if kind == "Delete":
                    target = safe_resolve_under(root, rel)
                    if target.exists():
                        target.unlink()
                    results.append({"path": rel, "op": "delete"})
                elif kind == "Add":
                    # body may be full content or +prefixed lines
                    lines = []
                    for ln in body.splitlines():
                        if ln.startswith("+") and not ln.startswith("+++"):
                            lines.append(ln[1:])
                        elif not ln.startswith("-") and not ln.startswith("@@") and not ln.startswith("***"):
                            lines.append(ln)
                    safe_write_text(root, rel, "\n".join(lines) + ("\n" if lines else ""))
                    results.append({"path": rel, "op": "add"})
                else:  # Update — try as unified hunks or full replace with + lines
                    target = safe_resolve_under(root, rel)
                    if not target.exists():
                        raise RuntimeError(f"update_missing:{rel}")
                    original = target.read_text(encoding="utf-8", errors="replace")
                    if "@@" in body:
                        updated = _apply_unified_to_text(original, body)
                    else:
                        # collect + lines as new content if no hunks
                        plus = [ln[1:] if ln.startswith("+") else ln for ln in body.splitlines() if not ln.startswith("-") and not ln.startswith("***")]
                        updated = "\n".join(plus) if plus else original
                    safe_write_text(root, rel, updated)
                    results.append({"path": rel, "op": "update"})
            if not results:
                raise RuntimeError("no_patch_blocks_parsed")
            return {"ok": True, "files": results, "count": len(results), "format": "begin_patch"}

        # Standard multi-file unified diff
        file_chunks = _re.split(r"(?=^--- )", patch, flags=_re.M)
        for chunk in file_chunks:
            chunk = chunk.strip()
            if not chunk.startswith("---"):
                continue
            lines = chunk.splitlines()
            if len(lines) < 2:
                continue
            old_line, new_line = lines[0], lines[1]
            # --- a/path or --- path
            def _parse_path(header: str) -> str:
                h = header[4:].strip() if header.startswith("--- ") or header.startswith("+++ ") else header
                if h.startswith("a/") or h.startswith("b/"):
                    h = h[2:]
                # strip timestamps
                h = h.split("\t")[0].strip()
                return h

            if not new_line.startswith("+++"):
                continue
            rel = _parse_path(new_line if not new_line.endswith("/dev/null") else old_line)
            if rel in {"/dev/null", "dev/null"}:
                rel = _parse_path(old_line)
            _backup(rel)
            if new_line.strip().endswith("/dev/null"):
                target = safe_resolve_under(root, rel)
                if target.exists():
                    target.unlink()
                results.append({"path": rel, "op": "delete"})
                continue
            if old_line.strip().endswith("/dev/null"):
                # new file from + lines
                content_lines = []
                for ln in lines[2:]:
                    if ln.startswith("+") and not ln.startswith("+++"):
                        content_lines.append(ln[1:])
                    elif ln.startswith("@@"):
                        continue
                safe_write_text(root, rel, "\n".join(content_lines) + "\n")
                results.append({"path": rel, "op": "add"})
                continue
            target = safe_resolve_under(root, rel)
            original = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
            updated = _apply_unified_to_text(original, "\n".join(lines[2:]))
            safe_write_text(root, rel, updated)
            results.append({"path": rel, "op": "update"})
        if not results:
            raise RuntimeError("no_unified_hunks_parsed")
        return {"ok": True, "files": results, "count": len(results), "format": "unified"}
    except Exception as exc:
        _rollback()
        return {"ok": False, "error": str(exc)[:500], "rolled_back": True, "partial": results}


def _apply_unified_to_text(original: str, hunk_text: str) -> str:
    """Apply unified diff hunks to original text. Raises on failure."""
    import re as _re
    src_lines = original.splitlines(keepends=True)
    # normalize to list without keepends for indexing
    src = original.splitlines()
    out: list[str] = []
    pos = 0
    hunks = list(_re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", hunk_text, flags=_re.M))
    if not hunks:
        # no hunks: treat + lines as full file
        plus = [ln[1:] for ln in hunk_text.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        if plus:
            return "\n".join(plus) + "\n"
        return original

    lines = hunk_text.splitlines()
    i = 0
    while i < len(lines):
        m = _re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", lines[i])
        if not m:
            i += 1
            continue
        old_start = int(m.group(1))
        # copy unchanged prefix (1-indexed)
        while pos < old_start - 1 and pos < len(src):
            out.append(src[pos])
            pos += 1
        i += 1
        while i < len(lines) and not lines[i].startswith("@@"):
            ln = lines[i]
            if ln.startswith("\\"):  # "\ No newline at end of file"
                i += 1
                continue
            if ln.startswith(" "):
                # context — must match
                expected = ln[1:]
                if pos >= len(src) or src[pos] != expected:
                    # soft: still consume
                    if pos < len(src):
                        out.append(src[pos])
                        pos += 1
                    else:
                        out.append(expected)
                else:
                    out.append(src[pos])
                    pos += 1
            elif ln.startswith("-"):
                # delete
                if pos < len(src):
                    pos += 1
            elif ln.startswith("+"):
                out.append(ln[1:])
            else:
                # unknown line — ignore
                pass
            i += 1
    while pos < len(src):
        out.append(src[pos])
        pos += 1
    return "\n".join(out) + ("\n" if original.endswith("\n") else "")



def run_tool(work_dir: str, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch FS / multi-file tool by name."""
    args = dict(args or {})
    if name in {
        "browser_navigate", "browser_content", "browser_click",
        "browser_fill", "browser_screenshot", "run_skill",
    }:
        args.setdefault("work_dir", work_dir)
        return _dispatch_browser_or_skill(name, args)
    if "path" in args and args.get("path") is not None:
        args["path"] = _coerce_rel_path(work_dir, str(args.get("path") or "."))
    if name == "list_dir":
        return list_dir(work_dir, str(args.get("path") or "."))
    if name == "read_file":
        return read_file(work_dir, str(args.get("path") or ""))
    if name == "read_files":
        paths = args.get("paths") or args.get("files") or []
        if isinstance(paths, str):
            paths = [paths]
        return read_files(work_dir, list(paths))
    if name == "write_file":
        return write_file(
            work_dir,
            str(args.get("path") or ""),
            str(args.get("content") if args.get("content") is not None else ""),
        )
    if name in {"edit_file", "search_replace"}:
        return edit_file(
            work_dir,
            str(args.get("path") or ""),
            str(args.get("old_string") or args.get("old") or ""),
            str(args.get("new_string") if args.get("new_string") is not None else args.get("new") or ""),
            replace_all=bool(args.get("replace_all")),
        )
    if name == "apply_edits":
        return apply_edits(
            work_dir,
            list(args.get("edits") or []),
            atomic=bool(args.get("atomic", True)),
        )
    if name == "apply_patch":
        return apply_patch(work_dir, str(args.get("patch") or args.get("patch_text") or args.get("diff") or ""))
    if name in {"grep_codebase", "grep", "search"}:
        return grep_codebase(
            work_dir,
            str(args.get("pattern") or args.get("query") or ""),
            glob=str(args.get("glob") or "**/*"),
            max_matches=int(args.get("max_matches") or 50),
            case_insensitive=bool(args.get("case_insensitive") or args.get("i")),
        )
    if name in {"glob_files", "glob"}:
        return glob_files(
            work_dir,
            str(args.get("pattern") or args.get("glob") or "**/*"),
            max_results=int(args.get("max_results") or 200),
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
    if name == "find_symbol":
        from lumen.engine.services.cline_runtime.agent_code_intel import find_symbol
        return find_symbol(
            work_dir,
            str(args.get("name") or args.get("symbol") or ""),
            kind=str(args.get("kind") or ""),
            path_prefix=str(args.get("path_prefix") or args.get("path") or ""),
            max_results=int(args.get("max_results") or 30),
        )
    if name == "get_symbol_source":
        from lumen.engine.services.cline_runtime.agent_code_intel import get_symbol_source
        return get_symbol_source(
            work_dir,
            name=str(args.get("name") or args.get("symbol") or ""),
            path=str(args.get("path") or ""),
            symbol_id=str(args.get("symbol_id") or args.get("id") or ""),
        )
    if name in {"find_references", "find_refs"}:
        from lumen.engine.services.cline_runtime.agent_code_intel import find_references
        return find_references(
            work_dir,
            str(args.get("name") or args.get("symbol") or ""),
            max_results=int(args.get("max_results") or 40),
        )
    if name in {"blast_radius", "symbol_blast_radius"}:
        from lumen.engine.services.cline_runtime.agent_code_intel import symbol_blast_radius
        return symbol_blast_radius(
            work_dir,
            name=str(args.get("name") or args.get("symbol") or ""),
            path=str(args.get("path") or ""),
            max_depth=int(args.get("max_depth") or 3),
        )
    if name in {"code_search", "hybrid_search"}:
        from lumen.engine.services.cline_runtime.agent_code_intel import code_search
        return code_search(
            work_dir,
            str(args.get("query") or args.get("pattern") or ""),
            top_k=int(args.get("top_k") or 10),
        )
    if name == "finish":
        return {
            "ok": True,
            "finished": True,
            "summary": str(args.get("summary") or args.get("message") or ""),
        }
    return {"ok": False, "error": f"unknown_tool:{name}"}



__all__ = [
    # code intel tools dispatched via run_tool

    "apply_edits",
    "apply_patch",
    "edit_file",
    "glob_files",
    "grep_codebase",
    "list_dir",
    "read_file",
    "read_files",
    "run_tool",
    "tree",
    "write_file",
]


def run_skill_tool(name: str, arguments: dict | None = None) -> dict:
    """Dispatch to Skills registry (browser/MCP/local plugins)."""
    try:
        from lumen.engine.services.skills import run_skill
        return run_skill(name, arguments or {})
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def _dispatch_browser_or_skill(tool_name: str, args: dict) -> dict:
    """Real Playwright / Skills registry dispatch from agent loop."""
    args = dict(args or {})
    name = (tool_name or "").strip()
    if name.startswith("browser_"):
        flag = (os.getenv("BROWSER_USE_ENABLED") or "0").strip().lower()
        if flag not in {"1", "true", "yes", "on"}:
            return {"ok": False, "error": "browser_use_disabled: set BROWSER_USE_ENABLED=1"}
    try:
        if name == "browser_navigate":
            from lumen.engine.services.browser_use import browse_url
            return browse_url(
                str(args.get("url") or ""),
                session_id=args.get("session_id"),
                work_dir=str(args.get("work_dir") or ""),
            )
        if name == "browser_content":
            from lumen.engine.services.browser_use import get_content
            return get_content(str(args.get("session_id") or ""))
        if name == "browser_click":
            from lumen.engine.services.browser_use import click
            return click(str(args.get("session_id") or ""), str(args.get("selector") or ""))
        if name == "browser_fill":
            from lumen.engine.services.browser_use import fill
            return fill(
                str(args.get("session_id") or ""),
                str(args.get("selector") or ""),
                str(args.get("value") or ""),
            )
        if name == "browser_screenshot":
            from lumen.engine.services.browser_use import screenshot
            return screenshot(str(args.get("session_id") or ""), path=args.get("path"))
        if name == "run_skill":
            from lumen.engine.services.skills import run_skill
            return run_skill(str(args.get("name") or ""), dict(args.get("arguments") or args))
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
    return {"ok": False, "error": f"unknown_tool:{name}"}
