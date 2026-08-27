"""Git worktree isolation for parallel agents — Cursor / Claude Code 2026 standard.

Real `git worktree` (shared object DB, independent index + branch per task).
Merge uses git-native checkout of owned paths from the agent branch.
Repo-level lock serializes worktree add/remove (git is not fully concurrent-safe).
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")
# One lock per resolved repo root — git worktree metadata is process-global on the repo
_REPO_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _repo_lock(root: Path) -> threading.RLock:
    key = str(root.resolve())
    with _LOCKS_GUARD:
        if key not in _REPO_LOCKS:
            _REPO_LOCKS[key] = threading.RLock()
        return _REPO_LOCKS[key]


def _safe_task_id(task_id: str) -> str:
    s = _SAFE_ID.sub("-", str(task_id or "task").strip())[:64]
    return s or "task"


def _run_git(cwd: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def git_available() -> bool:
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def is_git_repo(path: Path) -> bool:
    try:
        r = _run_git(path, "rev-parse", "--is-inside-work-tree")
        return r.returncode == 0 and "true" in (r.stdout or "").lower()
    except Exception:
        return False


def ensure_git_repo(work_dir: Path) -> bool:
    """Ensure work_dir is a git repo with HEAD (required for worktree add)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if not git_available():
        return False

    with _repo_lock(work_dir):
        if is_git_repo(work_dir):
            r = _run_git(work_dir, "rev-parse", "HEAD")
            if r.returncode == 0:
                return True
            _run_git(work_dir, "add", "-A")
            r = _run_git(
                work_dir,
                "-c", "user.email=lumen@local",
                "-c", "user.name=Lumen",
                "commit", "--allow-empty", "-m", "chore: lumen initial",
            )
            return r.returncode == 0

        if _run_git(work_dir, "init").returncode != 0:
            return False
        _run_git(work_dir, "config", "user.email", "lumen@local")
        _run_git(work_dir, "config", "user.name", "Lumen")
        gi = work_dir / ".gitignore"
        lines: set[str] = set()
        if gi.is_file():
            lines = {ln for ln in gi.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()}
        for extra in (".worktrees/", ".parallel/", ".lumen/", "__pycache__/", ".venv/", "*.pyc"):
            lines.add(extra)
        gi.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")
        _run_git(work_dir, "add", "-A")
        r = _run_git(
            work_dir,
            "-c", "user.email=lumen@local",
            "-c", "user.name=Lumen",
            "commit", "--allow-empty", "-m", "chore: lumen initial",
        )
        return r.returncode == 0


@dataclass
class TaskWorkspace:
    task_id: str
    root: Path
    path: Path
    kind: str = "main"  # worktree | copy | main
    branch: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def isolated(self) -> bool:
        return self.kind in {"worktree", "copy"}


def acquire_task_workspace(
    work_dir: Path | str,
    task_id: str,
    *,
    use_isolation: bool = True,
) -> TaskWorkspace:
    """Create isolated workspace. Prefers git worktree; falls back to .parallel copy."""
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    tid = _safe_task_id(task_id)

    if not use_isolation:
        return TaskWorkspace(task_id=tid, root=root, path=root, kind="main")

    # World-class path: real git worktree only (Cursor/Claude). No shutil copy theatre.
    allow_copy = (str(__import__("os").environ.get("LUMEN_ALLOW_COPY_ISOLATION") or "0").strip().lower()
                  in {"1", "true", "yes", "on"})

    if ensure_git_repo(root):
        branch = f"agent/{tid}"
        wt_path = root / ".worktrees" / tid
        with _repo_lock(root):
            if wt_path.exists():
                _run_git(root, "worktree", "remove", "--force", str(wt_path))
                shutil.rmtree(wt_path, ignore_errors=True)
            _run_git(root, "branch", "-D", branch)
            wt_path.parent.mkdir(parents=True, exist_ok=True)
            r = _run_git(root, "worktree", "add", "-b", branch, str(wt_path))
            if r.returncode == 0 and wt_path.is_dir():
                logger.info("worktree acquired task=%s path=%s branch=%s", tid, wt_path, branch)
                return TaskWorkspace(
                    task_id=tid, root=root, path=wt_path, kind="worktree", branch=branch
                )
            err = (r.stderr or r.stdout or "worktree_add_failed")[:300]
            logger.error("git worktree failed: %s", err)
            if not allow_copy:
                return TaskWorkspace(
                    task_id=tid, root=root, path=root, kind="main",
                    errors=[f"worktree_failed:{err}"],
                )

    if not allow_copy:
        logger.error("git unavailable — isolation required but cannot create worktree")
        return TaskWorkspace(
            task_id=tid, root=root, path=root, kind="main",
            errors=["git_required_for_isolation"],
        )

    # Explicit opt-in only (LUMEN_ALLOW_COPY_ISOLATION=1) — not production default
    session = root / ".parallel" / tid
    if session.exists():
        shutil.rmtree(session, ignore_errors=True)
    session.mkdir(parents=True, exist_ok=True)
    for src in root.rglob("*"):
        if not src.is_file():
            continue
        if any(x in src.parts for x in (".parallel", ".worktrees", ".git", "__pycache__", ".venv", ".lumen")):
            continue
        rel = src.relative_to(root)
        dest = session / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dest)
        except Exception:
            pass
    logger.warning("copy isolation used (opt-in) task=%s", tid)
    return TaskWorkspace(task_id=tid, root=root, path=session, kind="copy")


def _git_checkout_owned(root: Path, branch: str, rel: str) -> bool:
    """Bring one path from agent branch into main worktree via git (native)."""
    # git checkout <branch> -- <path> operates on current worktree (root)
    r = _run_git(root, "checkout", branch, "--", rel)
    return r.returncode == 0


def merge_task_workspace(
    session: TaskWorkspace,
    owned_files: list[str] | None = None,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Merge owned paths from isolation into root (Cursor-style apply).

    Rules (world-class):
    - Prefer explicit owned_files from the planner (exclusive ownership).
    - If owned_files empty on a worktree: only paths changed on the agent branch
      vs main HEAD (git diff --name-only) — NEVER dump the whole tree.
    - Apply via `git checkout <branch> -- <path>` under repo lock.
    - strict=True: ok=False if any owned path missing after apply.
    """
    if not session.isolated:
        return {"ok": True, "kind": "main", "merged": [], "conflicts": [], "method": "none", "missing": []}

    root = session.root
    src_root = session.path
    merged: list[str] = []
    conflicts: list[str] = []
    missing: list[str] = []
    method = "copy"
    explicit = [str(f).replace("\\", "/").lstrip("./") for f in (owned_files or []) if str(f).strip()]
    # normalize backslashes properly
    explicit = [str(f).replace(chr(92), "/").lstrip("./") for f in (owned_files or []) if str(f).strip()]

    with _repo_lock(root):
        if session.kind == "worktree" and session.branch:
            # Commit agent work on its branch first
            _run_git(src_root, "add", "-A")
            _run_git(
                src_root,
                "-c", "user.email=lumen@local",
                "-c", "user.name=Lumen",
                "commit", "-m", f"agent({session.task_id}): parallel task",
                "--allow-empty",
            )

            files = list(explicit)
            if not files:
                # Diff-only discovery — never full-tree rglob (ownership blast radius)
                diff = _run_git(root, "diff", "--name-only", "HEAD", session.branch)
                if diff.returncode == 0 and (diff.stdout or "").strip():
                    files = [ln.strip().replace(chr(92), "/") for ln in diff.stdout.splitlines() if ln.strip()]
                else:
                    # fallback: new untracked in worktree relative to list-files
                    ls = _run_git(src_root, "ls-files", "--others", "--exclude-standard")
                    tracked = _run_git(src_root, "diff", "--name-only", "HEAD")
                    for blob in (ls.stdout or "", tracked.stdout or ""):
                        for ln in blob.splitlines():
                            rel = ln.strip().replace(chr(92), "/")
                            if rel and rel not in files:
                                files.append(rel)

            method = "git_checkout_branch"
            for rel in files:
                src = src_root / rel
                if not src.is_file():
                    missing.append(rel)
                    continue
                dest = root / rel
                if dest.is_file():
                    try:
                        if dest.read_bytes() != src.read_bytes():
                            conflicts.append(rel)
                    except Exception:
                        pass
                if _git_checkout_owned(root, session.branch, rel):
                    merged.append(rel)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(src, dest)
                        merged.append(rel)
                        method = "git_checkout+copy_fallback"
                    except Exception as exc:
                        conflicts.append(f"{rel}:{type(exc).__name__}")
                        missing.append(rel)

            _run_git(root, "add", "-A")
            _run_git(
                root,
                "-c", "user.email=lumen@local",
                "-c", "user.name=Lumen",
                "commit", "-m", f"merge(agent/{session.task_id}): apply owned paths",
                "--allow-empty",
            )
        else:
            method = "copy"
            files = list(explicit)
            if not files:
                # copy isolation without owned_files: only files present in session not in skip dirs
                for src in src_root.rglob("*"):
                    if not src.is_file():
                        continue
                    if any(x in src.parts for x in (".git", "__pycache__", ".venv")):
                        continue
                    rel = str(src.relative_to(src_root)).replace(chr(92), "/")
                    files.append(rel)
            for rel in files:
                src = src_root / rel
                if not src.is_file():
                    missing.append(rel)
                    continue
                dest = root / rel
                try:
                    if dest.is_file() and dest.read_bytes() != src.read_bytes():
                        conflicts.append(rel)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    merged.append(rel)
                except Exception as exc:
                    conflicts.append(f"{rel}:{type(exc).__name__}")
                    missing.append(rel)

    ok = True
    if strict and explicit:
        for rel in explicit:
            if not (root / rel).is_file():
                if rel not in missing:
                    missing.append(rel)
                ok = False
    if strict and missing and explicit:
        ok = False

    return {
        "ok": ok,
        "kind": session.kind,
        "merged": merged,
        "conflicts": conflicts,
        "missing": missing,
        "branch": session.branch,
        "method": method,
    }



def release_task_workspace(session: TaskWorkspace) -> None:
    if not session.isolated:
        return
    root = session.root
    path = session.path
    with _repo_lock(root):
        if session.kind == "worktree":
            _run_git(root, "worktree", "remove", "--force", str(path))
            if session.branch:
                _run_git(root, "branch", "-D", session.branch)
            shutil.rmtree(path, ignore_errors=True)
        elif session.kind == "copy":
            shutil.rmtree(path, ignore_errors=True)


def write_task_tree_disk(work_dir: Path | str, tree_dict: dict[str, Any]) -> Path:
    import json

    root = Path(work_dir)
    out = root / ".lumen" / "task_tree.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tree_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def read_task_tree_disk(work_dir: Path | str) -> dict[str, Any] | None:
    import json

    p = Path(work_dir) / ".lumen" / "task_tree.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def run_tasks_in_parallel(
    work_dir: Path | str,
    tasks: list[Any],
    runner: Any,
    *,
    max_workers: int = 4,
) -> list[dict[str, Any]]:
    """Run task callables concurrently, each in its own worktree.

    runner(task, session: TaskWorkspace) -> dict
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    root = Path(work_dir)
    results: list[dict[str, Any]] = []
    if not tasks:
        return results

    def _one(task: Any) -> dict[str, Any]:
        tid = str(getattr(task, "id", None) or task)
        session = acquire_task_workspace(root, tid, use_isolation=True)
        try:
            out = runner(task, session)
            if not isinstance(out, dict):
                out = {"ok": bool(out), "task_id": tid}
            out.setdefault("task_id", tid)
            out.setdefault("isolation", session.kind)
            return out
        finally:
            try:
                release_task_workspace(session)
            except Exception:
                pass

    workers = max(1, min(int(max_workers or 1), len(tasks)))
    if workers == 1:
        return [_one(t) for t in tasks]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_one, t): t for t in tasks}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as exc:
                t = futs[fut]
                results.append({
                    "ok": False,
                    "task_id": str(getattr(t, "id", t)),
                    "error": f"{type(exc).__name__}:{exc}",
                })
    return results






def snapshot_base_commit(work_dir, message: str = "chore: lumen parallel base snapshot") -> str | None:
    """Commit current main tree so all worktrees share the same base SHA (Cursor pattern)."""
    root = Path(work_dir)
    if not ensure_git_repo(root):
        return None
    with _repo_lock(root):
        _run_git(root, "add", "-A")
        r = _run_git(
            root,
            "-c", "user.email=lumen@local",
            "-c", "user.name=Lumen",
            "commit", "-m", message,
            "--allow-empty",
        )
        h = _run_git(root, "rev-parse", "HEAD")
        if h.returncode == 0:
            return (h.stdout or "").strip() or None
        return None


def owned_files_overlap(tasks: list) -> list:
    """Return list of (file, task_a, task_b) for overlapping owned files."""
    claim = {}
    overlaps = []
    for task in tasks:
        tid = str(getattr(task, "id", "") or "")
        for f in list(getattr(task, "files", None) or []):
            rel = str(f).replace(chr(92), "/").lstrip("./")
            if not rel:
                continue
            if rel in claim and claim[rel] != tid:
                overlaps.append((rel, claim[rel], tid))
            else:
                claim[rel] = tid
    return overlaps


def partition_wave_by_ownership(tasks: list) -> tuple:
    """Split wave into (parallel_safe, must_run_serial) by file ownership overlap."""
    overlaps = owned_files_overlap(tasks)
    if not overlaps:
        return list(tasks), []
    contested = set()
    for _rel, a, b in overlaps:
        contested.add(a)
        contested.add(b)
    parallel_safe = [t for t in tasks if str(getattr(t, "id", "")) not in contested]
    serial = [t for t in tasks if str(getattr(t, "id", "")) in contested]
    return parallel_safe, serial


def prune_worktrees(work_dir) -> dict:
    """Remove stale agent/* worktrees and branches under work_dir."""
    root = Path(work_dir)
    removed = []
    if not is_git_repo(root):
        return {"ok": True, "removed": []}
    with _repo_lock(root):
        r = _run_git(root, "worktree", "list", "--porcelain")
        lines = (r.stdout or "").splitlines()
        path = None
        for ln in lines:
            if ln.startswith("worktree "):
                path = ln.split(" ", 1)[1].strip()
            elif ln.startswith("branch ") and path:
                br = ln.split(" ", 1)[1].strip()
                norm = path.replace(chr(92), "/")
                if "/.worktrees/" in norm or br.startswith("refs/heads/agent/"):
                    _run_git(root, "worktree", "remove", "--force", path)
                    removed.append(path)
                path = None
        _run_git(root, "worktree", "prune")
        br = _run_git(root, "branch", "--list", "agent/*")
        for ln in (br.stdout or "").splitlines():
            name = ln.replace("*", "").strip()
            if name.startswith("agent/"):
                _run_git(root, "branch", "-D", name)
                removed.append("branch:" + name)
    return {"ok": True, "removed": removed}


__all__ = [
    "TaskWorkspace",
    "git_available",
    "is_git_repo",
    "ensure_git_repo",
    "acquire_task_workspace",
    "merge_task_workspace",
    "release_task_workspace",
    "write_task_tree_disk",
    "read_task_tree_disk",
    "run_tasks_in_parallel",
    "snapshot_base_commit",
    "owned_files_overlap",
    "partition_wave_by_ownership",
    "prune_worktrees",
]
