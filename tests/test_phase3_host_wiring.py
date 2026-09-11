"""Phase 3 end-to-end wiring: market_gate, prepare path, webhook apply."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from lumen.engine.services.hosting.market_gate import evaluate_market_gate
from lumen.hosting.webhook_manager import apply_to_instance, register_webhook


def test_market_gate_serverless_track(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "x" * 32)
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "0")
    monkeypatch.setenv("VERCEL_TOKEN", "vcel_test_token_value_here")
    g = evaluate_market_gate()
    assert g.track == "lumen_serverless"
    assert g.ok is True


def test_market_gate_serverless_missing_token(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.setenv("TBE_TOKEN_SECRET", "x" * 32)
    monkeypatch.setenv("TBE_ALLOW_LOCAL_PROCESS", "0")
    monkeypatch.delenv("VERCEL_TOKEN", raising=False)
    with patch(
        "lumen.engine.services.live_deployment.vercel_client.token_configured",
        return_value=False,
    ):
        g = evaluate_market_gate()
    assert g.ok is False
    assert any("VERCEL" in m or "منصة" in m for m in g.missing)


def test_register_webhook_uses_verify_path():
    with patch(
        "lumen.hosting.serverless_verify.set_webhook",
        return_value={"ok": True, "url": "https://b.example/api"},
    ), patch(
        "lumen.hosting.serverless_verify.get_webhook_info",
        return_value={"ok": True, "url": "https://b.example/api"},
    ):
        r = register_webhook("1:TOK", "https://b.example/api", secret="sec")
    assert r["ok"] and r.get("verified") is True


def test_register_webhook_requires_secret():
    r = register_webhook("1:TOK", "https://b.example/api", secret="")
    assert r["ok"] is False


def test_apply_skips_when_already_verified():
    inst = MagicMock()
    inst.sandbox_backend = "lumen_serverless"
    inst.public_base_url = "https://b.example"
    inst.status = "running"
    inst.last_diagnosis = {
        "verify_ok": True,
        "webhook_verified": True,
        "webhook_url": "https://b.example/api",
        "webhook_path": "/api",
        "webhook_secret": "sec",
    }
    with patch("lumen.hosting.webhook_manager.register_webhook") as reg:
        r = apply_to_instance(instance_id="i1", bot_token="1:T", inst=inst)
    reg.assert_not_called()
    assert r["registered"] is True
    assert r.get("already_verified") is True


def test_hostservice_prepare_serverless(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('t').build()\n"
        "application.run_polling()\n",
        encoding="utf-8",
    )
    from lumen.engine.services.hosting.prepare_runtime import prepare_project_for_serverless
    pr = prepare_project_for_serverless(tmp_path)
    assert pr.ok
    assert (tmp_path / "api" / "index.py").is_file()
