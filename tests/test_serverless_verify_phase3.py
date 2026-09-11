"""Phase 3 — health + setWebhook + getWebhookInfo lifecycle."""
from __future__ import annotations

from unittest.mock import patch

from lumen.hosting.serverless_verify import (
    STATE_FAILED,
    STATE_RUNNING,
    get_webhook_info,
    health_check_deployment,
    set_webhook,
    verify_serverless_bot,
)


def test_health_check_success():
    def fake_get(url, **kwargs):
        return {"ok": True, "status": 200, "data": {"ok": True, "service": "lumen-bot"}}

    with patch("lumen.hosting.serverless_verify.http_get_json", side_effect=fake_get):
        r = health_check_deployment("https://bot.example", webhook_path="/api", retries=1, delay_sec=0)
    assert r["ok"] is True


def test_health_check_retries_then_fail():
    with patch(
        "lumen.hosting.serverless_verify.http_get_json",
        return_value={"ok": False, "status": 503, "error": "http_503"},
    ):
        r = health_check_deployment("https://bot.example", retries=2, delay_sec=0)
    assert r["ok"] is False


def test_set_webhook_and_info(monkeypatch):
    calls = []

    def fake_api(token, method, payload=None, **kwargs):
        calls.append(method)
        if method == "setWebhook":
            assert payload["url"].startswith("https://")
            assert payload.get("secret_token") == "sec"
            return {"ok": True, "result": True}
        if method == "getWebhookInfo":
            return {"ok": True, "result": {"url": "https://bot.example/api", "pending_update_count": 0}}
        return {"ok": False}

    with patch("lumen.hosting.serverless_verify.telegram_api", side_effect=fake_api):
        reg = set_webhook("1:TOK", "https://bot.example/api", secret="sec")
        info = get_webhook_info("1:TOK")
    assert reg["ok"] and info["ok"]
    assert info["url"] == "https://bot.example/api"
    assert "setWebhook" in calls and "getWebhookInfo" in calls


def test_verify_full_success():
    with patch(
        "lumen.hosting.serverless_verify.health_check_deployment",
        return_value={"ok": True, "status": 200, "healthy_url": "https://bot.example/api"},
    ), patch(
        "lumen.hosting.serverless_verify.set_webhook",
        return_value={"ok": True, "url": "https://bot.example/api"},
    ), patch(
        "lumen.hosting.serverless_verify.get_webhook_info",
        return_value={"ok": True, "url": "https://bot.example/api", "pending_update_count": 0},
    ):
        r = verify_serverless_bot(
            bot_token="1:TOK",
            public_url="https://bot.example",
            webhook_path="/api",
            webhook_secret="s",
        )
    assert r.ok and r.state == STATE_RUNNING
    assert r.webhook_url == "https://bot.example/api"
    assert any(p.state == STATE_RUNNING and p.ok for p in r.phases)


def test_verify_webhook_mismatch_fails():
    with patch(
        "lumen.hosting.serverless_verify.health_check_deployment",
        return_value={"ok": True, "status": 200},
    ), patch(
        "lumen.hosting.serverless_verify.set_webhook",
        return_value={"ok": True},
    ), patch(
        "lumen.hosting.serverless_verify.get_webhook_info",
        return_value={"ok": True, "url": "https://wrong.example/hook"},
    ):
        r = verify_serverless_bot(
            bot_token="1:TOK",
            public_url="https://bot.example",
            webhook_path="/api",
        )
    assert not r.ok
    assert r.state == STATE_FAILED


def test_verify_register_fail():
    with patch(
        "lumen.hosting.serverless_verify.health_check_deployment",
        return_value={"ok": True},
    ), patch(
        "lumen.hosting.serverless_verify.set_webhook",
        return_value={"ok": False, "error": "nope"},
    ):
        r = verify_serverless_bot(bot_token="1:TOK", public_url="https://bot.example")
    assert not r.ok and r.state == STATE_FAILED


def test_orchestration_runs_verify(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.delenv("LUMEN_SERVERLESS_SKIP_VERIFY", raising=False)
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('t').build()\n",
        encoding="utf-8",
    )
    from lumen.engine.services.live_deployment.report_data import DEPLOY_RUNNING, DeploymentStatus
    from lumen.hosting.orchestration import start_host

    class FakeDriver:
        def deploy(self, project_path, *, env_vars=None, service_name=""):
            return DeploymentStatus(
                provider="lumen_serverless",
                deployment_id="dpl_v3",
                status=DEPLOY_RUNNING,
                url="https://live.example",
                message="deployed",
            )

    with patch("lumen.engine.services.live_deployment.vercel_client.token_configured", return_value=True), patch(
        "lumen.engine.services.live_deployment.vercel_process_driver.VercelProcessDriver",
        return_value=FakeDriver(),
    ), patch(
        "lumen.hosting.serverless_verify.health_check_deployment",
        return_value={"ok": True, "status": 200, "healthy_url": "https://live.example/api"},
    ), patch(
        "lumen.hosting.serverless_verify.set_webhook",
        return_value={"ok": True, "url": "https://live.example/api"},
    ), patch(
        "lumen.hosting.serverless_verify.get_webhook_info",
        return_value={"ok": True, "url": "https://live.example/api"},
    ):
        backend, handle = start_host(
            project_path=str(tmp_path),
            bot_token="9:ABC",
            user_id=1,
            service_name="lumen-u1-b1",
        )
    assert handle.ok
    assert handle.status == "running"
    assert handle.meta.get("lifecycle_state") == STATE_RUNNING
    assert handle.meta.get("verify_ok") is True
    assert "vercel" not in (handle.message or "").lower()
