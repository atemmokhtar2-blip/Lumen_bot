"""Phase B — real git worktree isolation for parallel agents."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from lumen.engine.services.multi_agent.worktree_isolation import (
    acquire_task_workspace,
    ensure_git_repo,
    git_available,
    merge_task_workspace,
    read_task_tree_disk,
    release_task_workspace,
    write_task_tree_disk,
)


def test_git_available():
    assert git_available() is True


def test_parallel_worktrees_no_collision():
    wd = Path(tempfile.mkdtemp(prefix="wt_iso_"))
    try:
        (wd / "main.py").write_text("print(1)\n", encoding="utf-8")
        assert ensure_git_repo(wd)
        a = acquire_task_workspace(wd, "task_a", use_isolation=True)
        b = acquire_task_workspace(wd, "task_b", use_isolation=True)
        assert a.kind == "worktree"
        assert b.kind == "worktree"
        assert a.path != b.path
        (a.path / "fa.py").write_text("A\n", encoding="utf-8")
        (b.path / "fb.py").write_text("B\n", encoding="utf-8")
        merge_task_workspace(a, owned_files=["fa.py"])
        merge_task_workspace(b, owned_files=["fb.py"])
        assert (wd / "fa.py").read_text(encoding="utf-8") == "A\n"
        assert (wd / "fb.py").read_text(encoding="utf-8") == "B\n"
        release_task_workspace(a)
        release_task_workspace(b)
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def test_task_tree_disk():
    wd = Path(tempfile.mkdtemp(prefix="wt_tree_"))
    try:
        write_task_tree_disk(wd, {"goal": "g", "tasks": [{"id": "1"}]})
        d = read_task_tree_disk(wd)
        assert d is not None
        assert d["goal"] == "g"
        assert d["tasks"][0]["id"] == "1"
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def test_no_isolation_returns_main():
    wd = Path(tempfile.mkdtemp(prefix="wt_main_"))
    try:
        s = acquire_task_workspace(wd, "x", use_isolation=False)
        assert s.kind == "main"
        assert s.path == wd
    finally:
        shutil.rmtree(wd, ignore_errors=True)
