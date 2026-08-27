"""Worker context layers: task packet + workspace context."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.multi_agent.coding_agent import (
    build_task_packet,
    build_worker_context,
    step_budget,
)


def test_step_budget_elevated():
    assert step_budget() >= 16
    assert step_budget(repair=True) >= 16


def test_task_packet_includes_acceptance():
    p = build_task_packet(
        goal="build bot",
        task_brief="scaffold main",
        acceptance=["main.py exists", "token from env"],
        target_files=["main.py", "requirements.txt"],
    )
    assert "ACCEPTANCE CRITERIA" in p
    assert "main.py exists" in p
    assert "TARGET FILES" in p
    assert "finish" in p.lower()


def test_worker_context_preread(tmp_path: Path):
    (tmp_path / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    ctx = build_worker_context(tmp_path, "inspect main", target_files=["main.py"])
    assert "main.py" in ctx["pre_read_files"]
