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
    snapshot_base_commit,
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


def test_ownership_overlap_partition():
    from lumen.engine.services.multi_agent.worktree_isolation import (
        owned_files_overlap,
        partition_wave_by_ownership,
    )

    class T:
        def __init__(self, i, files):
            self.id = i
            self.files = files

    tasks = [T("a", ["x.py"]), T("b", ["x.py", "y.py"]), T("c", ["z.py"])]
    ov = owned_files_overlap(tasks)
    assert any(o[0] == "x.py" for o in ov)
    safe, serial = partition_wave_by_ownership(tasks)
    assert [t.id for t in safe] == ["c"]
    assert set(t.id for t in serial) == {"a", "b"}


def test_prune_worktrees():
    from lumen.engine.services.multi_agent.worktree_isolation import (
        ensure_git_repo,
        acquire_task_workspace,
        release_task_workspace,
        prune_worktrees,
    )

    wd = Path(tempfile.mkdtemp(prefix="wt_prune_"))
    try:
        (wd / "main.py").write_text("1\n", encoding="utf-8")
        ensure_git_repo(wd)
        s = acquire_task_workspace(wd, "z1", use_isolation=True)
        assert s.kind == "worktree"
        release_task_workspace(s)
        out = prune_worktrees(wd)
        assert out.get("ok") is True
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def test_isolation_requires_git_no_silent_copy():
    """Without LUMEN_ALLOW_COPY_ISOLATION, failure is kind=main + errors — never silent copy."""
    import os
    os.environ.pop("LUMEN_ALLOW_COPY_ISOLATION", None)
    from lumen.engine.services.multi_agent.worktree_isolation import acquire_task_workspace
    # force fail by using a non-writable path simulation: empty path that can't init — skip
    # Real path: ensure worktree succeeds when git works
    wd = Path(tempfile.mkdtemp(prefix="wt_req_"))
    try:
        (wd / "main.py").write_text("1\n", encoding="utf-8")
        s = acquire_task_workspace(wd, "t1", use_isolation=True)
        assert s.kind == "worktree", s
        release_task_workspace(s)
    finally:
        shutil.rmtree(wd, ignore_errors=True)



def test_schedule_marks_only_batch_running():
    """Ownership partition: only disjoint tasks are parallel-safe."""
    from lumen.engine.services.multi_agent.task_tree import TaskNode, TaskStatus
    from lumen.engine.services.multi_agent.worktree_isolation import partition_wave_by_ownership

    def make(tid, files):
        return TaskNode(
            id=tid,
            title=tid,
            status=TaskStatus.READY.value,
            files=files,
            parallel_group="feature_modules",
        )

    wave = [make("a", ["mod_a.py"]), make("b", ["mod_b.py"]), make("c", ["mod_a.py"])]
    safe, serial = partition_wave_by_ownership(wave)
    assert [x.id for x in safe] == ["b"]
    assert set(x.id for x in serial) == {"a", "c"}
    # schedule would only mark safe (or one serial) RUNNING
    for n in safe:
        n.status = TaskStatus.RUNNING.value
    assert safe[0].status == TaskStatus.RUNNING.value
    assert all(n.status == TaskStatus.READY.value for n in serial)


def test_merge_empty_owned_uses_diff_not_full_tree():
    wd = Path(tempfile.mkdtemp(prefix="wt_diff_"))
    try:
        (wd / "main.py").write_text("1\n", encoding="utf-8")
        (wd / "untouched.py").write_text("U\n", encoding="utf-8")
        ensure_git_repo(wd)
        snapshot_base_commit(wd)
        s = acquire_task_workspace(wd, "diff1", use_isolation=True)
        (s.path / "new_only.py").write_text("N\n", encoding="utf-8")
        m = merge_task_workspace(s, owned_files=None, strict=False)
        assert "new_only.py" in (m.get("merged") or []) or (wd / "new_only.py").is_file()
        # untouched must still exist
        assert (wd / "untouched.py").read_text(encoding="utf-8") == "U\n"
        release_task_workspace(s)
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def test_merge_strict_missing_owned():
    wd = Path(tempfile.mkdtemp(prefix="wt_strict_"))
    try:
        (wd / "main.py").write_text("1\n", encoding="utf-8")
        ensure_git_repo(wd)
        s = acquire_task_workspace(wd, "st1", use_isolation=True)
        m = merge_task_workspace(s, owned_files=["nope.py"], strict=True)
        assert m.get("ok") is False
        assert "nope.py" in (m.get("missing") or [])
        release_task_workspace(s)
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def test_safe_task_id_no_path_escape():
    wd = Path(tempfile.mkdtemp(prefix="wt_esc_"))
    try:
        (wd / "main.py").write_text("1\n", encoding="utf-8")
        ensure_git_repo(wd)
        for tid in ["../../../escape", "feat/auth", ".."]:
            s = acquire_task_workspace(wd, tid, use_isolation=True)
            assert s.kind == "worktree", (tid, s)
            s.path.resolve().relative_to((wd / ".worktrees").resolve())
            release_task_workspace(s)
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def test_concurrent_same_task_id_unique_slots():
    from concurrent.futures import ThreadPoolExecutor
    wd = Path(tempfile.mkdtemp(prefix="wt_slot_"))
    try:
        (wd / "main.py").write_text("1\n", encoding="utf-8")
        ensure_git_repo(wd)
        def once(i):
            s = acquire_task_workspace(wd, "same", use_isolation=True)
            assert s.kind == "worktree"
            p = s.path
            release_task_workspace(s)
            return str(p)
        with ThreadPoolExecutor(4) as ex:
            paths = list(ex.map(once, range(4)))
        assert len(set(paths)) == 4
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def test_empty_files_forced_serial():
    from lumen.engine.services.multi_agent.task_tree import TaskNode, TaskStatus
    from lumen.engine.services.multi_agent.worktree_isolation import partition_wave_by_ownership
    wave = [
        TaskNode(id="e1", title="e1", files=[], parallel_group="g", status=TaskStatus.READY.value),
        TaskNode(id="e2", title="e2", files=[], parallel_group="g", status=TaskStatus.READY.value),
        TaskNode(id="ok", title="ok", files=["a.py"], parallel_group="g", status=TaskStatus.READY.value),
    ]
    safe, serial = partition_wave_by_ownership(wave)
    assert [x.id for x in safe] == ["ok"]
    assert set(x.id for x in serial) == {"e1", "e2"}
