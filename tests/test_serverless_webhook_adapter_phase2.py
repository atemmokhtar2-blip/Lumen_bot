"""Phase 2 strong — neutralize polling, scrub tokens, validate layout, secrets."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from lumen.hosting.serverless_webhook_adapter import (
    FRAMEWORK_PTB,
    MODE_POLLING,
    _ADAPTER_MARKER,
    adapt_project_for_serverless,
    detect_project,
    neutralize_polling_calls,
    scrub_hardcoded_tokens,
    validate_serverless_layout,
)
from lumen.engine.services.hosting.prepare_runtime import prepare_project_for_serverless
from lumen.engine.services.live_deployment.report_data import DEPLOY_RUNNING, DeploymentStatus
from lumen.hosting.orchestration import start_host


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


def test_neutralize_polling(tmp_path):
    f = tmp_path / "main.py"
    f.write_text(
        "application.run_polling()\nbot.infinity_polling()\nprint('ok')\n",
        encoding="utf-8",
    )
    assert neutralize_polling_calls(f) is True
    text = f.read_text(encoding="utf-8")
    assert "LUMEN_POLLING_NEUTRALIZED_V1" in text
    assert "run_polling()" not in text or "pass" in text
    assert neutralize_polling_calls(f) is False  # idempotent


def test_scrub_hardcoded_token(tmp_path):
    f = tmp_path / "bot.py"
    f.write_text(
        'TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"\nprint(TOKEN)\n',
        encoding="utf-8",
    )
    n = scrub_hardcoded_tokens(f)
    assert n >= 1
    assert "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw" not in f.read_text(encoding="utf-8")


def test_adapt_full_pipeline(tmp_path):
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "TOKEN = '123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw'\n"
        "application = Application.builder().token(TOKEN).build()\n"
        "application.run_polling()\n",
        encoding="utf-8",
    )
    r = adapt_project_for_serverless(tmp_path, entry_point="main.py")
    assert r.ok, r.message
    ok, why = validate_serverless_layout(tmp_path)
    assert ok, why
    api = (tmp_path / "api" / "index.py").read_text(encoding="utf-8")
    assert _ADAPTER_MARKER in api
    assert "class handler" in api
    assert "_install_polling_stubs" in api
    assert "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw" not in api
    main = (tmp_path / "main.py").read_text(encoding="utf-8")
    assert "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw" not in main
    assert "LUMEN_POLLING_NEUTRALIZED_V1" in main


def test_adapt_idempotent_valid(tmp_path):
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('t').build()\n",
        encoding="utf-8",
    )
    a = adapt_project_for_serverless(tmp_path)
    b = adapt_project_for_serverless(tmp_path)
    assert a.ok and b.ok
    assert b.details.get("skipped") == "already_adapted"


def test_prepare_serverless(tmp_path):
    (tmp_path / "main.py").write_text(
        "import telebot\nbot = telebot.TeleBot('x')\nbot.infinity_polling()\n",
        encoding="utf-8",
    )
    pr = prepare_project_for_serverless(tmp_path)
    assert pr.ok
    assert pr.details.get("serverless") is True


def test_orchestration_injects_webhook_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.setenv("LUMEN_SERVERLESS_SKIP_VERIFY", "1")
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('t').build()\n"
        "application.run_polling()\n",
        encoding="utf-8",
    )
    captured = {}

    class FakeDriver:
        name = "lumen_serverless"

        def deploy(self, project_path, *, env_vars=None, service_name=""):
            captured["env"] = dict(env_vars or {})
            assert (Path(project_path) / "api" / "index.py").is_file()
            return DeploymentStatus(
                provider="lumen_serverless",
                deployment_id="dpl_p2s",
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
    assert captured["env"].get("TELEGRAM_WEBHOOK_SECRET")
    assert handle.meta.get("webhook_secret")
    assert "/api" in (handle.meta.get("webhook_url") or "")
