"""Phase 6 strong — multi-signal serverless health + monitor."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from lumen.engine.services.hosting.health_monitor import check_instance, run_once
from lumen.hosting.serverless_health import evaluate_serverless_instance, HealthReport


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


def test_evaluate_all_signals_ok():
    inst = _Inst()
    with patch(
        "lumen.hosting.serverless_health.probe_platform_status",
        return_value=(True, "platform_ready", {"platform_status": "running"}),
    ), patch(
        "lumen.hosting.serverless_health.probe_http_adapter",
        return_value=(True, "http_ok", {"adapter_ok": True}),
    ), patch(
        "lumen.hosting.serverless_health.probe_telegram_webhook",
        return_value=(True, "telegram_ok", {"telegram_checked": True}),
    ):
        r = evaluate_serverless_instance(inst)
    assert r.ok
    assert r.reason == "all_signals_ok"


def test_evaluate_fails_on_platform():
    inst = _Inst()
    with patch(
        "lumen.hosting.serverless_health.probe_platform_status",
        return_value=(False, "platform_error", {}),
    ), patch(
        "lumen.hosting.serverless_health.probe_http_adapter",
        return_value=(True, "http_ok", {}),
    ), patch(
        "lumen.hosting.serverless_health.probe_telegram_webhook",
        return_value=(True, "telegram_skipped_no_token", {"telegram_checked": False}),
    ):
        r = evaluate_serverless_instance(inst)
    assert not r.ok
    assert "platform" in r.reason


def test_evaluate_telegram_mismatch_when_checked():
    inst = _Inst()
    with patch(
        "lumen.hosting.serverless_health.probe_platform_status",
        return_value=(True, "platform_ready", {}),
    ), patch(
        "lumen.hosting.serverless_health.probe_http_adapter",
        return_value=(True, "http_ok", {}),
    ), patch(
        "lumen.hosting.serverless_health.probe_telegram_webhook",
        return_value=(False, "telegram_webhook_mismatch", {"telegram_checked": True}),
    ):
        r = evaluate_serverless_instance(inst)
    assert not r.ok
    assert "telegram" in r.reason


def test_check_instance_uses_evaluate():
    inst = _Inst()
    with patch(
        "lumen.hosting.serverless_health.evaluate_serverless_instance",
        return_value=HealthReport(ok=True, reason="all_signals_ok", signals={"http": {"ok": True}}),
    ):
        ok, reason = check_instance(inst)
    assert ok
    assert inst.last_diagnosis.get("last_health_ok") is True


def test_run_once_marks_failed(monkeypatch):
    monkeypatch.setenv("TBE_HOST_AUTO_REPAIR", "0")
    inst = _Inst()
    svc = MagicMock()
    svc._instances = {"i1": inst}
    svc._save = MagicMock()
    with patch(
        "lumen.engine.services.hosting.health_monitor.check_instance",
        return_value=(False, "platform_down+http_unhealthy"),
    ):
        stats = run_once(svc)
    assert stats["failed"] == 1
    assert inst.status == "failed"


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
