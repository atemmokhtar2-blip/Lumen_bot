"""Phase 1 complete: lumen_serverless is a real host backend via orchestration."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from lumen.hosting.orchestration import resolve_backend_name, start_host, stop_host
from lumen.engine.services.live_deployment.vercel_client import ApiResult
from lumen.engine.services.live_deployment.report_data import DeploymentStatus, DEPLOY_RUNNING


def test_resolve_default_firecracker(monkeypatch):
    monkeypatch.delenv("TBE_HOST_BACKEND", raising=False)
    assert resolve_backend_name() == "firecracker"


def test_resolve_serverless_aliases(monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.setenv("LUMEN_SERVERLESS_SKIP_VERIFY", "1")
    monkeypatch.setenv("ENVIRONMENT", "test")
    assert resolve_backend_name() == "lumen_serverless"
    monkeypatch.setenv("TBE_HOST_BACKEND", "serverless")
    assert resolve_backend_name() == "lumen_serverless"
    monkeypatch.setenv("TBE_HOST_BACKEND", "vercel")
    assert resolve_backend_name() == "lumen_serverless"


def test_start_serverless_without_token_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.setenv("LUMEN_SERVERLESS_SKIP_VERIFY", "1")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("VERCEL_TOKEN", raising=False)
    (tmp_path / "app.py").write_text("x", encoding="utf-8")
    with patch("lumen.engine.services.live_deployment.vercel_client.token_configured", return_value=False):
        backend, handle = start_host(
            project_path=str(tmp_path),
            bot_token="1:AA",
            user_id=1,
            service_name="lumen-u1-b1",
        )
    assert backend.name == "lumen_serverless"
    assert handle.status == "failed"
    assert handle.ok is False
    assert "vercel" not in (handle.message or "").lower()


def test_start_serverless_success_mocked(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.setenv("LUMEN_SERVERLESS_SKIP_VERIFY", "1")
    monkeypatch.setenv("ENVIRONMENT", "test")
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('t').build()\n"
        "application.run_polling()\n",
        encoding="utf-8",
    )

    class FakeDriver:
        name = "lumen_serverless"

        def deploy(self, project_path, *, env_vars=None, service_name=""):
            assert "BOT_TOKEN" in (env_vars or {})
            return DeploymentStatus(
                provider="lumen_serverless",
                deployment_id="dpl_live_1",
                project_id="prj_1",
                service_id=service_name,
                status=DEPLOY_RUNNING,
                url="https://lumen-bot.example",
                message="البوت يعمل على استضافة Lumen.",
            )

    with patch("lumen.engine.services.live_deployment.vercel_client.token_configured", return_value=True):
        with patch(
            "lumen.engine.services.live_deployment.vercel_process_driver.VercelProcessDriver",
            return_value=FakeDriver(),
        ):
            backend, handle = start_host(
                project_path=str(tmp_path),
                bot_token="123:TOKEN",
                user_id=42,
                service_name="lumen-u42-b1",
            )
    assert backend.name == "lumen_serverless"
    assert handle.ok
    assert handle.deployment_id == "dpl_live_1"
    assert handle.meta.get("url", "").startswith("https://")
    assert "vercel" not in handle.message.lower()


def test_stop_serverless_calls_driver():
    calls = []

    class FakeDriver:
        def stop(self, deployment_id):
            calls.append(deployment_id)
            return DeploymentStatus(provider="lumen_serverless", status="stopped")

    with patch(
        "lumen.engine.services.live_deployment.vercel_process_driver.VercelProcessDriver",
        return_value=FakeDriver(),
    ):
        stop_host("dpl_x", backend="lumen_serverless")
    assert calls == ["dpl_x"]
