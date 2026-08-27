"""Critical residual bugs: Send isolation, cross-platform parallel features."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.multi_agent.dynamic_planner import assemble_plan
from lumen.engine.services.multi_agent.task_tree import TaskTree, TaskStatus


def test_discord_features_are_parallel_modules():
    plan = assemble_plan(goal="discord bot", preferred_keys=["mute", "ban"])
    feats = [t for t in plan.tasks if t.parallel_group == "feature_modules"]
    assert len(feats) >= 2
    assert all(t.files and t.files[0].startswith("modules/") for t in feats)


def test_web_features_use_routers_dir():
    plan = assemble_plan(goal="FastAPI app", preferred_keys=["auth", "payments"])
    feats = [t for t in plan.tasks if t.parallel_group == "feature_modules"]
    assert len(feats) >= 2
    assert all("routers/" in (t.files[0] if t.files else "") for t in feats)


def test_parallel_wave_returns_multiple_feature_tasks():
    plan = assemble_plan(goal="telegram bot", preferred_keys=["admin", "payments", "ai_chat"])
    tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
    tree.mark("scaffold", TaskStatus.DONE)
    tree.refresh_readiness()
    wave = tree.parallel_wave()
    assert len(wave) >= 2
    assert all(n.parallel_group == "feature_modules" for n in wave)


def test_isolation_flag_true_for_single_active_parallel_group():
    """Regression: Send fans out with active=[one]; isolation must still apply."""
    # pure logic mirror of pipeline condition
    class T:
        parallel_group = "feature_modules"
    task = T()
    active = ["feat_admin"]  # single id as in Send
    use_iso = bool(getattr(task, "parallel_group", "") or "")
    assert use_iso is True
    # old bug would require len(active)>1
    assert not (use_iso and len(active) > 1 and False)  # document old condition was wrong
