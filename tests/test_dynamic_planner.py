"""Layered dynamic planner tests — intent, features, workspace, graphs."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.multi_agent.dynamic_planner import (
    assemble_plan,
    classify_intent,
    extract_features,
    probe_workspace,
)
from lumen.engine.services.multi_agent.plan_contract import build_plan_from_spec
from lumen.engine.services.multi_agent.task_tree import TaskTree


def test_intent_telegram():
    i = classify_intent("اعمل بوت تيليجرام للترحيب")
    assert i.kind == "telegram_bot"
    assert i.platform == "telegram"


def test_intent_discord():
    i = classify_intent("create a discord moderation bot")
    assert i.kind == "discord_bot"


def test_intent_web_api():
    i = classify_intent("build a FastAPI service with auth")
    assert i.kind == "web_api"


def test_intent_whatsapp():
    i = classify_intent("واتساب بوت للرد الآلي")
    assert i.kind == "whatsapp_bot"


def test_features_extracted():
    feats = extract_features("بوت فيه admin و payments و database", ["inline_keyboard"])
    assert "inline_keyboard" in feats
    assert "admin" in feats
    assert "payments" in feats
    assert "database" in feats


def test_workspace_refine(tmp_path: Path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    snap = probe_workspace(tmp_path)
    assert snap.is_refine is True
    plan = assemble_plan(goal="أصلح البوت", work_dir=tmp_path)
    ids = [t.id for t in plan.tasks]
    assert "inspect" in ids or "patch" in ids
    assert "mode:incremental_repair" in plan.constraints


def test_discord_plan_not_telegram_template():
    plan = assemble_plan(goal="discord bot with mute command")
    titles = " ".join(t.title for t in plan.tasks).lower()
    assert "discord" in titles
    assert any("discord" in c for c in plan.constraints) or plan.version == "dyn1"


def test_web_plan_routes():
    plan = assemble_plan(goal="FastAPI app with health endpoint")
    ids = [t.id for t in plan.tasks]
    assert "scaffold" in ids
    assert "wire_features" in ids or "routes" in ids or "implement" in ids


def test_depends_on_honored():
    plan = assemble_plan(goal="telegram bot with admin feature", preferred_keys=["admin"])
    tree = TaskTree.from_execution_plan(plan, goal=plan.goal)
    # features must depend on scaffold, not arbitrary linear only
    feat = next((n for n in tree.nodes.values() if n.id == "features"), None)
    if feat:
        assert "scaffold" in (feat.depends_on or [])


def test_build_plan_from_spec_uses_dynamic():
    plan = build_plan_from_spec(goal="whatsapp support bot", features=["faq"])
    assert plan.version == "dyn1"
    assert any("whatsapp" in str(c) or "intent:whatsapp" in str(c) for c in plan.constraints)
