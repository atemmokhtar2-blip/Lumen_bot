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
            logger.warning("git worktree failed (%s) — copy fallback", err)

    # Copy fallback
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
    logger.info("copy workspace acquired task=%s path=%s", tid, session)
    return TaskWorkspace(task_id=tid, root=root, path=session, kind="copy")


def _git_checkout_owned(root: Path, branch: str, rel: str) -> bool:
    """Bring one path from agent branch into main worktree via git (native)."""
    # git checkout <branch> -- <path> operates on current worktree (root)
    r = _run_git(root, "checkout", branch, "--", rel)
    return r.returncode == 0


def merge_task_workspace(
    session: TaskWorkspace,
    owned_files: list[str] | None = None,
) -> dict[str, Any]:
    """Merge owned files from isolation back into root.

    Worktree path: commit on agent branch, then `git checkout <branch> -- <files>`
    into the main worktree (Cursor-style apply of owned paths).
    """
    if not session.isolated:
        return {"ok": True, "kind": "main", "merged": [], "conflicts": [], "method": "none"}

    root = session.root
    src_root = session.path
    merged: list[str] = []
    conflicts: list[str] = []
    method = "copy"
    files = [str(f).replace("\\", "/").lstrip("./") for f in (owned_files or []) if str(f).strip()]

    if not files:
        for src in src_root.rglob("*"):
            if not src.is_file():
                continue
            if any(x in src.parts for x in (".git", "__pycache__", ".venv")):
                continue
            files.append(str(src.relative_to(src_root)).replace("\\", "/"))

    with _repo_lock(root):
        if session.kind == "worktree" and session.branch:
            # Commit agent work on its branch
            _run_git(src_root, "add", "-A")
            _run_git(
                src_root,
                "-c", "user.email=lumen@local",
                "-c", "user.name=Lumen",
                "commit", "-m", f"agent({session.task_id}): parallel task",
                "--allow-empty",
            )
            method = "git_checkout_branch"
            for rel in files:
                src = src_root / rel
                if not src.is_file():
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
                    # Fallback file copy for this path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(src, dest)
                        merged.append(rel)
                        method = "git_checkout+copy_fallback"
                    except Exception as exc:
                        conflicts.append(f"{rel}:{type(exc).__name__}")
            # Record merge commit on main for audit
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
            for rel in files:
                src = src_root / rel
                if not src.is_file():
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

    return {
        "ok": True,
        "kind": session.kind,
        "merged": merged,
        "conflicts": conflicts,
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
]
