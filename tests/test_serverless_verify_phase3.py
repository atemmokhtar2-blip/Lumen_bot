"""Phase 3 strict — health adapter JSON, getMe, setWebhook, exact getWebhookInfo."""
from __future__ import annotations

from unittest.mock import patch

from lumen.hosting.serverless_verify import (
    STATE_FAILED,
    STATE_RUNNING,
    allow_skip_verify,
    get_webhook_info,
    health_check_deployment,
    set_webhook,
    urls_equivalent,
    verify_serverless_bot,
)


def test_urls_equivalent():
    assert urls_equivalent("https://A.example/api", "https://a.example/api/")
    assert not urls_equivalent("https://a.example/api", "https://b.example/api")


def test_allow_skip_only_non_prod(monkeypatch):
    monkeypatch.setenv("LUMEN_SERVERLESS_SKIP_VERIFY", "1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    # under pytest this may still be set by runner — force CI/env
    # when PYTEST is set allow_skip returns True; test production gate separately
    monkeypatch.setenv("ENVIRONMENT", "test")
    assert allow_skip_verify() is True
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("CI", raising=False)
    # If pytest injects PYTEST_CURRENT_TEST, allow_skip stays true — that's intentional for tests
    # Production gate without pytest:
    with patch.dict("os.environ", {"LUMEN_SERVERLESS_SKIP_VERIFY": "1", "ENVIRONMENT": "production"}, clear=False):
        with patch("lumen.hosting.serverless_verify.os.environ.get", side_effect=lambda k, d=None: {
            "LUMEN_SERVERLESS_SKIP_VERIFY": "1",
            "ENVIRONMENT": "production",
            "TBE_ENV": "",
            "PYTEST_CURRENT_TEST": "",
            "CI": "",
        }.get(k, d)):
            assert allow_skip_verify() is False


def test_health_requires_adapter_json():
    # bare 200 HTML is not enough
    with patch(
        "lumen.hosting.serverless_verify.http_request",
        return_value={"ok": True, "status": 200, "data": {"_raw": "<html>"}},
    ):
        r = health_check_deployment("https://bot.example", retries=1, delay_sec=0)
    assert r["ok"] is False

    with patch(
        "lumen.hosting.serverless_verify.http_request",
        return_value={
            "ok": True,
            "status": 200,
            "data": {"ok": True, "service": "lumen-bot", "token_configured": True},
        },
    ):
        r = health_check_deployment("https://bot.example", retries=1, delay_sec=0)
    assert r["ok"] is True
    assert r.get("adapter_ok") is True


def test_set_webhook_requires_secret():
    r = set_webhook("1:TOK", "https://bot.example/api", secret="")
    assert r["ok"] is False
    assert r["error"] == "secret_required"


def test_set_webhook_and_info_unwrap():
    def fake_http(url, **kwargs):
        if "setWebhook" in url:
            return {"ok": True, "status": 200, "data": {"ok": True, "result": True}}
        if "getWebhookInfo" in url:
            return {
                "ok": True,
                "status": 200,
                "data": {"ok": True, "result": {"url": "https://bot.example/api", "pending_update_count": 0}},
            }
        return {"ok": False, "status": 500, "error": "x"}

    with patch("lumen.hosting.serverless_verify.http_request", side_effect=fake_http):
        reg = set_webhook("1:TOK", "https://bot.example/api", secret="sec")
        info = get_webhook_info("1:TOK")
    assert reg["ok"] is True
    assert info["ok"] is True
    assert info["url"] == "https://bot.example/api"


def test_verify_full_success():
    with patch(
        "lumen.hosting.serverless_verify.health_check_deployment",
        return_value={"ok": True, "status": 200, "healthy_url": "https://bot.example/api", "adapter_ok": True},
    ), patch(
        "lumen.hosting.serverless_verify.telegram_get_me",
        return_value={"ok": True, "username": "mybot", "id": 1, "is_bot": True},
    ), patch(
        "lumen.hosting.serverless_verify.delete_webhook",
        return_value={"ok": True},
    ), patch(
        "lumen.hosting.serverless_verify.set_webhook",
        return_value={"ok": True, "url": "https://bot.example/api", "attempt": 1},
    ), patch(
        "lumen.hosting.serverless_verify.get_webhook_info",
        return_value={"ok": True, "url": "https://bot.example/api", "pending_update_count": 0},
    ):
        r = verify_serverless_bot(
            bot_token="1:TOK",
            public_url="https://bot.example",
            webhook_path="/api",
            webhook_secret="secretvalue",
        )
    assert r.ok and r.state == STATE_RUNNING
    assert r.details.get("webhook_verified") is True


def test_verify_health_fail_is_hard():
    with patch(
        "lumen.hosting.serverless_verify.health_check_deployment",
        return_value={"ok": False, "error": "adapter_health_not_confirmed"},
    ):
        r = verify_serverless_bot(
            bot_token="1:TOK",
            public_url="https://bot.example",
            webhook_secret="s",
        )
    assert not r.ok and r.state == STATE_FAILED


def test_verify_mismatch_fail():
    with patch(
        "lumen.hosting.serverless_verify.health_check_deployment",
        return_value={"ok": True},
    ), patch(
        "lumen.hosting.serverless_verify.telegram_get_me",
        return_value={"ok": True, "username": "b"},
    ), patch(
        "lumen.hosting.serverless_verify.delete_webhook", return_value={"ok": True}
    ), patch(
        "lumen.hosting.serverless_verify.set_webhook", return_value={"ok": True}
    ), patch(
        "lumen.hosting.serverless_verify.get_webhook_info",
        return_value={"ok": True, "url": "https://other.example/x"},
    ):
        r = verify_serverless_bot(
            bot_token="1:TOK",
            public_url="https://bot.example",
            webhook_secret="s",
        )
    assert not r.ok and r.state == STATE_FAILED


def test_orchestration_requires_ready_and_verify(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("LUMEN_SERVERLESS_SKIP_VERIFY", raising=False)
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('t').build()\n",
        encoding="utf-8",
    )
    from lumen.engine.services.live_deployment.report_data import DEPLOY_RUNNING, DeploymentStatus
    from lumen.hosting.orchestration import start_host

    class FakeDriver:
        def deploy(self, *a, **k):
            return DeploymentStatus(
                provider="lumen_serverless",
                deployment_id="dpl_v3",
                status=DEPLOY_RUNNING,
                url="https://live.example",
                message="deployed",
            )

    with patch(
        "lumen.engine.services.live_deployment.vercel_client.token_configured", return_value=True
    ), patch(
        "lumen.engine.services.live_deployment.vercel_process_driver.VercelProcessDriver",
        return_value=FakeDriver(),
    ), patch(
        "lumen.hosting.serverless_verify.health_check_deployment",
        return_value={"ok": True, "adapter_ok": True, "healthy_url": "https://live.example/api"},
    ), patch(
        "lumen.hosting.serverless_verify.telegram_get_me",
        return_value={"ok": True, "username": "x"},
    ), patch(
        "lumen.hosting.serverless_verify.delete_webhook", return_value={"ok": True}
    ), patch(
        "lumen.hosting.serverless_verify.set_webhook",
        return_value={"ok": True, "url": "https://live.example/api"},
    ), patch(
        "lumen.hosting.serverless_verify.get_webhook_info",
        return_value={"ok": True, "url": "https://live.example/api"},
    ):
        backend, handle = start_host(
            project_path=str(tmp_path), bot_token="9:ABC", user_id=1, service_name="lumen-u1-b1"
        )
    assert handle.ok and handle.status == "running"
    assert handle.meta.get("verify_ok") is True
    assert handle.meta.get("lifecycle_state") == STATE_RUNNING


def test_orchestration_pending_is_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.delenv("LUMEN_SERVERLESS_SKIP_VERIFY", raising=False)
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('t').build()\n",
        encoding="utf-8",
    )
    from lumen.engine.services.live_deployment.report_data import DEPLOY_PENDING, DeploymentStatus
    from lumen.hosting.orchestration import start_host

    class FakeDriver:
        def deploy(self, *a, **k):
            return DeploymentStatus(
                provider="lumen_serverless",
                deployment_id="dpl_p",
                status=DEPLOY_PENDING,
                url="https://live.example",
                message="pending",
            )

    with patch(
        "lumen.engine.services.live_deployment.vercel_client.token_configured", return_value=True
    ), patch(
        "lumen.engine.services.live_deployment.vercel_process_driver.VercelProcessDriver",
        return_value=FakeDriver(),
    ):
        backend, handle = start_host(
            project_path=str(tmp_path), bot_token="9:ABC", user_id=1, service_name="lumen-u1-b1"
        )
    assert handle.status == "failed"
    assert handle.ok is False
