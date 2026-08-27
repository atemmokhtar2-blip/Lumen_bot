"""Deep tests for planner parallel features, isolation merge, acceptance v3."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.multi_agent.dynamic_planner import assemble_plan
from lumen.engine.services.multi_agent.task_tree import TaskTree
from lumen.engine.services.multi_agent.acceptance_check import (
    evaluate_task,
    feature_mentioned_in_sources,
    check_compileall,
)


def test_planner_splits_features_into_parallel_tasks():
    plan = assemble_plan(goal="telegram bot", preferred_keys=["admin", "payments", "ai_chat"])
    ids = [t.id for t in plan.tasks]
    # multiple feat_* with parallel_group
    feat_tasks = [t for t in plan.tasks if (t.parallel_group or "") == "feature_modules"]
    assert len(feat_tasks) >= 2
    assert all(t.depends_on == ["scaffold"] for t in feat_tasks)
    assert "wire_features" in ids
    wire = next(t for t in plan.tasks if t.id == "wire_features")
    assert set(wire.depends_on) >= {t.id for t in feat_tasks}


def test_task_tree_preserves_parallel_group():
    plan = assemble_plan(goal="telegram moderation bot", preferred_keys=["admin", "moderation"])
    tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
    groups = [n.parallel_group for n in tree.nodes.values() if n.parallel_group]
    assert "feature_modules" in groups


def test_feature_must_appear_in_sources(tmp_path: Path):
    (tmp_path / "main.py").write_text("def start():\n    return 1\n", encoding="utf-8")
    assert feature_mentioned_in_sources(tmp_path, "admin") is False
    (tmp_path / "modules").mkdir()
    (tmp_path / "modules" / "admin.py").write_text("def admin_panel():\n    return True\n", encoding="utf-8")
    assert feature_mentioned_in_sources(tmp_path, "admin") is True


def test_compileall_stdlib(tmp_path: Path):
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    r = check_compileall(tmp_path)
    assert r["ok"] is True


def test_acceptance_feature_working_criterion(tmp_path: Path):
    (tmp_path / "main.py").write_text("import os\nx=os.getenv('T')\n", encoding="utf-8")
    (tmp_path / "modules").mkdir()
    (tmp_path / "modules" / "payments.py").write_text("def charge():\n    return 1\n", encoding="utf-8")
    r = evaluate_task(
        tmp_path,
        files=["modules/payments.py"],
        acceptance=["modules/payments.py exists", "feature working: payments"],
        strict=True,
    )
    assert r["ok"] is True, r.get("failed")
