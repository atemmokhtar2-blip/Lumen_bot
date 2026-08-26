"""Phase D hard generation — medium difficulty end-to-end quality."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.evaluation.hard_generation import (
    HARD_SPECS,
    run_hard_generation_scenario,
)
from lumen.engine.services.evaluation.quality_score import score_generated_project


def test_hard_specs_cover_platforms():
    plats = {x["platform"] for x in HARD_SPECS}
    assert {"telegram", "discord", "whatsapp", "web"} <= plats


def test_hard_telegram_pipeline(tmp_path: Path):
    item = next(x for x in HARD_SPECS if x["id"] == "tg_support_tickets")
    r = run_hard_generation_scenario(
        tmp_path / "tg",
        platform=item["platform"],
        spec=item["spec"],
        scenario_id=item["id"],
    )
    assert r["attempts"] >= 4
    assert r["latency_s"] > 0.001  # more work than pure contract
    assert r["metrics"]["quality_score"] is not None
    assert float(r["metrics"]["quality_score"]) >= 0.55
    assert r["success"] is True


def test_hard_discord_pipeline(tmp_path: Path):
    item = next(x for x in HARD_SPECS if x["platform"] == "discord")
    r = run_hard_generation_scenario(
        tmp_path / "dc",
        platform=item["platform"],
        spec=item["spec"],
        scenario_id=item["id"],
    )
    assert r["success"] is True
    assert r["metrics"]["quality_checks"].get("platform_marker") is True


def test_quality_score_rejects_empty(tmp_path: Path):
    q = score_generated_project(tmp_path, platform="telegram", spec="ticket system")
    assert q["ok"] is False
    assert q["score"] < 0.7
