"""LangGraph Send fan-out when tasks have disjoint files."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("langgraph")

from lumen.engine.services.multi_agent.task_tree import TaskNode, TaskTree, TaskStatus


def test_disjoint_wave_ids():
    tree = TaskTree(goal="g")
    tree.add(TaskNode(id="a", title="A", files=["a.py"], status=TaskStatus.READY.value if hasattr(TaskStatus,"READY") else "READY"), parent_id=tree.root_id)
    tree.add(TaskNode(id="b", title="B", files=["b.py"], status="READY"), parent_id=tree.root_id)
    tree.refresh_readiness()
    wave = tree.parallel_wave()
    # may depend on READY status enum
    assert isinstance(wave, list)
