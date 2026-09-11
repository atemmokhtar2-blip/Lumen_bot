"""Phase 6 — serverless health probe + auto-repair path."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from lumen.engine.services.hosting.health_monitor import check_instance, run_once


@dataclass
class _Inst:
    instance_id: str = "i1"
    user_id: int = 1
    status: str = "running"
    sandbox_backend: str = "lumen_serverless"
    deployment_id: str = "dpl_1"
    public_base_url: str = "https://bot.example"
    webhook_public_url: str = "https://bot.example/api"
    project_path: str = "/tmp/p"
    tenant_id: str = "tg:1"
    last_error: str = ""
    last_health_at: float = 0.0
    last_diagnosis: dict = field(default_factory=lambda: {"webhook_path": "/api"})


def test_serverless_probe_healthy():
    inst = _Inst()
    with patch(
        "lumen.hosting.serverless_verify.health_check_deployment",
        return_value={"ok": True, "adapter_ok": True},
    ):
        ok, reason = check_instance(inst)
    assert ok and reason == "http_ok"


def test_serverless_probe_unhealthy():
    inst = _Inst()
    with patch(
        "lumen.hosting.serverless_verify.health_check_deployment",
        return_value={"ok": False, "error": "adapter_health_not_confirmed"},
    ):
        ok, reason = check_instance(inst)
    assert not ok


def test_run_once_marks_failed_without_auto_repair(monkeypatch):
    monkeypatch.setenv("TBE_HOST_AUTO_REPAIR", "0")
    inst = _Inst()
    svc = MagicMock()
    svc._instances = {"i1": inst}
    svc._save = MagicMock()
    with patch(
        "lumen.engine.services.hosting.health_monitor.check_instance",
        return_value=(False, "http_down"),
    ):
        stats = run_once(svc)
    assert stats["failed"] == 1
    assert inst.status == "failed"
    assert "health_failed" in inst.last_error


def test_run_once_auto_repair(monkeypatch):
    monkeypatch.setenv("TBE_HOST_AUTO_REPAIR", "1")
    monkeypatch.setenv("TBE_HOST_REPAIR_COOLDOWN", "1")
    inst = _Inst()
    svc = MagicMock()
    svc._instances = {"i1": inst}
    svc._save = MagicMock()
    from lumen.hosting.serverless_repair import RepairResult

    with patch(
        "lumen.engine.services.hosting.health_monitor.check_instance",
        return_value=(False, "http_down"),
    ), patch(
        "lumen.hosting.secrets_env.load_project_secrets",
        return_value={"BOT_TOKEN": "1:TOK"},
    ), patch(
        "lumen.hosting.serverless_repair.repair_serverless_project",
        return_value=RepairResult(
            ok=True,
            message="fixed",
            deployment_id="dpl_new",
            url="https://new.example",
            meta={"lifecycle_state": "RUNNING", "verify_ok": True, "webhook_url": "https://new.example/api"},
        ),
    ), patch(
        "lumen.hosting.agent_host_pipeline.attach_serverless_instance",
        return_value=inst,
    ):
        stats = run_once(svc)
    assert stats["repaired"] == 1
    assert inst.status == "running"
