"""Phase 5 — agent host pipeline + status formatting."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from lumen.hosting.agent_host_pipeline import (
    PipelineResult,
    format_instances_status,
    run_host_pipeline,
)


@dataclass
class _Inst:
    instance_id: str = "i1"
    status: str = "running"
    sandbox_backend: str = "lumen_serverless"
    public_base_url: str = "https://x.example"
    last_diagnosis: dict = field(default_factory=lambda: {"lifecycle_state": "RUNNING", "verify_ok": True})


def test_format_instances_status():
    text = format_instances_status([_Inst()])
    assert "سريعة" in text
    assert "RUNNING" in text or "التحقق" in text
    assert "vercel" not in text.lower()


def test_pipeline_missing_token():
    r = run_host_pipeline(user_id=1, project_path="/tmp", bot_token="")
    assert not r.ok
    assert r.data.get("needs_bot_token") is True


def test_pipeline_missing_path(tmp_path):
    r = run_host_pipeline(user_id=1, project_path=str(tmp_path / "nope"), bot_token="1:TOK")
    assert not r.ok


def test_pipeline_success_mocked(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    (tmp_path / "main.py").write_text("x", encoding="utf-8")

    inst = _Inst()
    host_result = MagicMock()
    host_result.ok = True
    host_result.instance = inst
    host_result.message = "ok"
    host_result.to_user_text = lambda: "البوت يعمل على استضافة Lumen."

    svc = MagicMock()
    svc.start.return_value = host_result
    svc.list_for_user.return_value = []

    with patch("lumen.engine.services.hosting.get_hosting_service", return_value=svc), patch(
        "lumen.hosting.serverless_policy.count_serverless_running", return_value=0
    ), patch(
        "lumen.hosting.serverless_policy.assert_serverless_quota", return_value=(True, "ok")
    ):
        r = run_host_pipeline(user_id=7, project_path=str(tmp_path), bot_token="1:ABC", tenant_id="tg:7")
    assert r.ok
    assert r.instance_id == "i1"
    assert r.lifecycle_state == "RUNNING"
    svc.start.assert_called_once()


def test_pipeline_repair_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    (tmp_path / "main.py").write_text("x", encoding="utf-8")

    host_result = MagicMock()
    host_result.ok = False
    host_result.instance = None
    host_result.message = "fail"
    host_result.to_user_text = lambda: "فشل"

    svc = MagicMock()
    svc.start.return_value = host_result
    svc.list_for_user.return_value = []

    from lumen.hosting.serverless_repair import RepairResult

    with patch("lumen.engine.services.hosting.get_hosting_service", return_value=svc), patch(
        "lumen.hosting.serverless_policy.count_serverless_running", return_value=0
    ), patch(
        "lumen.hosting.serverless_policy.assert_serverless_quota", return_value=(True, "ok")
    ), patch(
        "lumen.hosting.serverless_repair.repair_serverless_project",
        return_value=RepairResult(
            ok=True,
            message="تم الإصلاح",
            deployment_id="dpl_r",
            url="https://fixed.example",
            meta={"lifecycle_state": "RUNNING", "verify_ok": True, "webhook_url": "https://fixed.example/api"},
        ),
    ):
        r = run_host_pipeline(user_id=1, project_path=str(tmp_path), bot_token="1:T")
    assert r.ok
    assert r.data.get("repaired") is True
    assert r.deployment_id == "dpl_r"
