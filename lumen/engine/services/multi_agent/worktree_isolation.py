"""Git worktree isolation for parallel agent tasks (Cursor / Claude Code 2026 pattern).

World-class parallel agents use real `git worktree` — not file copies into `.parallel/`.
Each task gets its own branch + working directory sharing the same object DB.

API:
  session = acquire_task_workspace(work_dir, task_id, use_isolation=True)
  # ... run coding agent in session.path ...
  merge_task_workspace(session, owned_files=[...])
  release_task_workspace(session)

Fallback: if git is unavailable, uses a copy workspace under `.parallel/` (same merge contract).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_task_id(task_id: str) -> str:
    s = _SAFE_ID.sub("-", str(task_id or "task").strip())[:64]
    return s or "task"


def _run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
        check=False if not check else False,
    )


def git_available() -> bool:
    try:
        r = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
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
    """Ensure work_dir is a git repo with at least one commit (required for worktree add)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if not git_available():
        return False
    if is_git_repo(work_dir):
        # Ensure HEAD exists
        r = _run_git(work_dir, "rev-parse", "HEAD")
        if r.returncode == 0:
            return True
        # empty repo — make initial commit
        _run_git(work_dir, "add", "-A")
        r = _run_git(
            work_dir,
            "-c",
            "user.email=lumen@local",
            "-c",
            "user.name=Lumen",
            "commit",
            "--allow-empty",
            "-m",
            "chore: lumen initial",
        )
        return r.returncode == 0

    r = _run_git(work_dir, "init")
    if r.returncode != 0:
        return False
    _run_git(work_dir, "config", "user.email", "lumen@local")
    _run_git(work_dir, "config", "user.name", "Lumen")
    # ignore worktree/parallel dirs
    gitignore = work_dir / ".gitignore"
    lines = set()
    if gitignore.is_file():
        lines = set(gitignore.read_text(encoding="utf-8", errors="ignore").splitlines())
    for extra in (".worktrees/", ".parallel/", "__pycache__/", ".venv/", "*.pyc"):
        lines.add(extra)
    gitignore.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")
    _run_git(work_dir, "add", "-A")
    r = _run_git(
        work_dir,
        "-c",
        "user.email=lumen@local",
        "-c",
        "user.name=Lumen",
        "commit",
        "--allow-empty",
        "-m",
        "chore: lumen initial",
    )
    return r.returncode == 0


@dataclass
class TaskWorkspace:
    """Isolated workspace for one parallel task."""

    task_id: str
    root: Path  # main project work_dir
    path: Path  # where the agent should write
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
    """Create an isolated workspace for a parallel task.

    Prefers real `git worktree add`. Falls back to `.parallel/` copy if git fails.
    When use_isolation is False, returns the main work_dir (kind=main).
    """
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    tid = _safe_task_id(task_id)

    if not use_isolation:
        return TaskWorkspace(task_id=tid, root=root, path=root, kind="main")

    # Prefer git worktree (Cursor / Claude Code pattern)
    if ensure_git_repo(root):
        branch = f"agent/{tid}"
        wt_path = root / ".worktrees" / tid
        # Clean previous
        if wt_path.exists():
            _run_git(root, "worktree", "remove", "--force", str(wt_path))
            shutil.rmtree(wt_path, ignore_errors=True)
        # Drop stale branch if exists
        _run_git(root, "branch", "-D", branch)
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        r = _run_git(root, "worktree", "add", "-b", branch, str(wt_path))
        if r.returncode == 0 and wt_path.is_dir():
            logger.info("worktree acquired task=%s path=%s branch=%s", tid, wt_path, branch)
            return TaskWorkspace(
                task_id=tid,
                root=root,
                path=wt_path,
                kind="worktree",
                branch=branch,
            )
        err = (r.stderr or r.stdout or "worktree_add_failed")[:300]
        logger.warning("git worktree failed (%s) — copy fallback", err)

    # Fallback: file copy isolation (legacy .parallel)
    session = root / ".parallel" / tid
    if session.exists():
        shutil.rmtree(session, ignore_errors=True)
    session.mkdir(parents=True, exist_ok=True)
    for src in root.rglob("*"):
        if not src.is_file():
            continue
        if any(x in src.parts for x in (".parallel", ".worktrees", ".git", "__pycache__", ".venv")):
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


def merge_task_workspace(
    session: TaskWorkspace,
    owned_files: list[str] | None = None,
) -> dict[str, Any]:
    """Merge owned files from isolated workspace back into root.

    For worktree: copy owned files from worktree path → root (task ownership model).
    Also attempts a commit on the agent branch for auditability.
    """
    if not session.isolated:
        return {"ok": True, "kind": "main", "merged": [], "conflicts": []}

    root = session.root
    src_root = session.path
    merged: list[str] = []
    conflicts: list[str] = []
    files = list(owned_files or [])

    if not files:
        # Discover new/changed files relative to isolation root
        for src in src_root.rglob("*"):
            if not src.is_file():
                continue
            if any(x in src.parts for x in (".git", "__pycache__", ".venv")):
                continue
            rel = str(src.relative_to(src_root)).replace("\\", "/")
            files.append(rel)

    for rel in files:
        rel_n = str(rel).replace("\\", "/").lstrip("./")
        src = src_root / rel_n
        if not src.is_file():
            continue
        dest = root / rel_n
        try:
            if dest.is_file() and dest.read_bytes() != src.read_bytes():
                # overlapping edit — still take task-owned file
                conflicts.append(rel_n)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            merged.append(rel_n)
        except Exception as exc:
            conflicts.append(f"{rel_n}:{type(exc).__name__}")

    # Audit commit on agent branch when worktree
    if session.kind == "worktree" and session.branch:
        _run_git(src_root, "add", "-A")
        _run_git(
            src_root,
            "-c",
            "user.email=lumen@local",
            "-c",
            "user.name=Lumen",
            "commit",
            "-m",
            f"agent({session.task_id}): parallel task",
            "--allow-empty",
        )

    return {
        "ok": True,
        "kind": session.kind,
        "merged": merged,
        "conflicts": conflicts,
        "branch": session.branch,
    }


def release_task_workspace(session: TaskWorkspace) -> None:
    """Remove worktree or copy workspace after merge."""
    if not session.isolated:
        return
    root = session.root
    path = session.path
    if session.kind == "worktree":
        _run_git(root, "worktree", "remove", "--force", str(path))
        if session.branch:
            _run_git(root, "branch", "-D", session.branch)
        shutil.rmtree(path, ignore_errors=True)
    elif session.kind == "copy":
        shutil.rmtree(path, ignore_errors=True)


def write_task_tree_disk(work_dir: Path | str, tree_dict: dict[str, Any]) -> Path:
    """Persist TaskTree for workers (Planner writes; Worker reads brief from disk)."""
    root = Path(work_dir)
    out = root / ".lumen" / "task_tree.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    import json

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
]
