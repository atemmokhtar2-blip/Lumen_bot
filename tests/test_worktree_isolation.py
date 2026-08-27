"""Phase B — world-class git worktree isolation."""
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
    run_tasks_in_parallel,
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
        m1 = merge_task_workspace(a, owned_files=["fa.py"])
        m2 = merge_task_workspace(b, owned_files=["fb.py"])
        assert m1.get("method", "").startswith("git_checkout")
        assert (wd / "fa.py").read_text(encoding="utf-8") == "A\n"
        assert (wd / "fb.py").read_text(encoding="utf-8") == "B\n"
        release_task_workspace(a)
        release_task_workspace(b)
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def test_run_tasks_in_parallel_concurrent():
    wd = Path(tempfile.mkdtemp(prefix="wt_par_"))
    try:
        (wd / "main.py").write_text("x=1\n", encoding="utf-8")
        assert ensure_git_repo(wd)

        class T:
            def __init__(self, i):
                self.id = f"t{i}"

        def runner(task, session):
            p = session.path / f"{task.id}.py"
            p.write_text(f"V{task.id}\n", encoding="utf-8")
            merge_task_workspace(session, owned_files=[f"{task.id}.py"])
            return {"ok": True, "task_id": task.id, "isolation": session.kind}

        tasks = [T(i) for i in range(3)]
        results = run_tasks_in_parallel(wd, tasks, runner, max_workers=3)
        assert len(results) == 3
        assert all(r.get("ok") for r in results)
        assert all(r.get("isolation") == "worktree" for r in results)
        for i in range(3):
            assert (wd / f"t{i}.py").is_file()
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def test_task_tree_disk():
    wd = Path(tempfile.mkdtemp(prefix="wt_tree_"))
    try:
        write_task_tree_disk(wd, {"goal": "g", "tasks": [{"id": "1"}]})
        d = read_task_tree_disk(wd)
        assert d is not None
        assert d["goal"] == "g"
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
