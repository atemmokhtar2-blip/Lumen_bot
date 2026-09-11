"""Phase 6 strong — durable instance scan, real logs shape, host_heal tool."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from lumen.engine.services.hosting.health_monitor import run_once
from lumen.engine.services.live_deployment.vercel_process_driver import VercelProcessDriver
from lumen.engine.services.live_deployment.vercel_client import ApiResult


@dataclass
class _Inst:
    instance_id: str = "i1"
    user_id: int = 1
    status: str = "running"
    sandbox_backend: str = "lumen_serverless"
    deployment_id: str = "dpl_AbC123xyz"
    public_base_url: str = "https://bot.example"
    webhook_public_url: str = "https://bot.example/api"
    project_path: str = "/tmp/p"
    tenant_id: str = "tg:1"
    last_error: str = ""
    last_health_at: float = 0.0
    last_diagnosis: dict = field(default_factory=dict)
    started_at: float = 1.0


def test_run_once_uses_iter_running_instances(monkeypatch):
    monkeypatch.setenv("TBE_HOST_AUTO_REPAIR", "0")
    inst = _Inst()
    svc = MagicMock()
    svc.iter_running_instances.return_value = [inst]
    svc._instances = {}
    svc._save = MagicMock()
    with patch(
        "lumen.engine.services.hosting.health_monitor.check_instance",
        return_value=(False, "http_unhealthy"),
    ):
        stats = run_once(svc)
    assert stats["checked"] == 1
    assert stats["failed"] == 1
    svc.iter_running_instances.assert_called()


def test_vercel_logs_parses_events():
    driver = VercelProcessDriver()
    driver._client = MagicMock()
    driver._client.configured = True
    driver._client.list_deployment_events.return_value = ApiResult(
        ok=True,
        data=[
            {"text": "Building", "created": "1"},
            {"text": "Ready", "created": "2"},
        ],
    )
    # deployment id must match _ID_RE
    lines = driver.logs("dpl_abcdefghijklmnopqrstuv", limit=10)
    assert any("Ready" in x for x in lines)


def test_host_heal_in_registry():
    from lumen.engine.services.tool_runtime.registry import TOOL_SPECS
    assert "host_heal" in TOOL_SPECS
    assert "host_diagnose" in TOOL_SPECS
