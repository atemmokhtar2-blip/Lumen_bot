"""Phase 2 — detect + generate webhook adapter for Lumen serverless."""
from __future__ import annotations

from pathlib import Path

from lumen.hosting.serverless_webhook_adapter import (
    FRAMEWORK_PTB,
    MODE_POLLING,
    adapt_project_for_serverless,
    detect_project,
)
from lumen.engine.services.hosting.prepare_runtime import prepare_project_for_serverless


def test_detect_ptb_polling(tmp_path):
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('x').build()\n"
        "application.run_polling()\n",
        encoding="utf-8",
    )
    d = detect_project(tmp_path)
    assert d.framework == FRAMEWORK_PTB
    assert d.mode == MODE_POLLING
    assert d.entry_point == "main.py"


def test_adapt_writes_handler_without_token(tmp_path):
    (tmp_path / "bot.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('x').build()\n"
        "application.run_polling()\n",
        encoding="utf-8",
    )
    r = adapt_project_for_serverless(tmp_path, entry_point="bot.py")
    assert r.ok
    assert "api/index.py" in r.files_written
    assert "vercel.json" in r.files_written
    api = (tmp_path / "api" / "index.py").read_text(encoding="utf-8")
    assert "LUMEN_SERVERLESS_WEBHOOK_ADAPTER_V1" in api
    assert "BOT_TOKEN" in api
    assert "123456:ABC" not in api
    assert 'os.environ.get("BOT_TOKEN")' in api
    cfg = (tmp_path / "vercel.json").read_text(encoding="utf-8")
    assert "api/index.py" in cfg
    meta = (tmp_path / ".lumen_serverless.json").read_text(encoding="utf-8")
    assert "python-telegram-bot" in meta


def test_adapt_idempotent(tmp_path):
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\napplication = Application.builder().token('t').build()\n",
        encoding="utf-8",
    )
    a = adapt_project_for_serverless(tmp_path)
    b = adapt_project_for_serverless(tmp_path)
    assert a.ok and b.ok
    assert b.details.get("skipped") == "already_adapted" or b.detect.already_adapted


def test_prepare_project_for_serverless(tmp_path):
    (tmp_path / "main.py").write_text(
        "import telebot\nbot = telebot.TeleBot('x')\nbot.infinity_polling()\n",
        encoding="utf-8",
    )
    pr = prepare_project_for_serverless(tmp_path)
    assert pr.ok
    assert pr.details.get("serverless") is True
    assert (tmp_path / "api" / "index.py").is_file()
    assert "LUMEN_SERVERLESS" in pr.env_vars


def test_orchestration_prepare_before_deploy(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('t').build()\n"
        "application.run_polling()\n",
        encoding="utf-8",
    )
    from unittest.mock import patch
    from lumen.engine.services.live_deployment.report_data import DeploymentStatus, DEPLOY_RUNNING
    from lumen.hosting.orchestration import start_host

    class FakeDriver:
        name = "lumen_serverless"

        def deploy(self, project_path, *, env_vars=None, service_name=""):
            assert (Path(project_path) / "api" / "index.py").is_file()
            return DeploymentStatus(
                provider="lumen_serverless",
                deployment_id="dpl_p2",
                status=DEPLOY_RUNNING,
                url="https://example.lumen-host.app",
                message="البوت يعمل على استضافة Lumen.",
            )

    with patch("lumen.engine.services.live_deployment.vercel_client.token_configured", return_value=True):
        with patch(
            "lumen.engine.services.live_deployment.vercel_process_driver.VercelProcessDriver",
            return_value=FakeDriver(),
        ):
            backend, handle = start_host(
                project_path=str(tmp_path),
                bot_token="1:TOK",
                user_id=7,
                service_name="lumen-u7-b1",
            )
    assert handle.ok
    assert handle.meta.get("webhook_path") == "/api"
    assert "/api" in (handle.meta.get("webhook_url") or "")
