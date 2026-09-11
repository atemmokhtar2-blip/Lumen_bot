"""Phase E — real monitoring + targeted penetration probes."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_ENV", "test")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("SECURITY_EVENTS_DIR", str(tmp_path / "sec"))
    monkeypatch.setenv("SECURITY_EVENTS_ENABLED", "1")
    monkeypatch.setenv("SECURITY_ALERT_LOG_ONLY", "1")
    monkeypatch.setenv("SECURITY_ALERT_LOG_ONLY_ACK", "I_ACCEPT_SECURITY_ALERTS_LOG_ONLY")
    monkeypatch.setenv("SECURITY_ALERT_COOLDOWN_SEC", "0")
    try:
        from lumen.platform.security_metrics import reset_for_tests
        reset_for_tests()
    except Exception:
        pass
    try:
        from lumen.platform import security_alerts as sa
        sa._RECENT.clear()
        sa._last_sent.clear()
    except Exception:
        pass


def test_emit_admin_rejected_records_metric_and_alert(tmp_path, monkeypatch):
    monkeypatch.setenv("SECURITY_EVENTS_DIR", str(tmp_path / "sec"))
    from lumen.platform.security_events import emit
    from lumen.platform.security_metrics import snapshot
    from lumen.platform.security_alerts import recent_alerts

    emit("auth.admin_rejected", severity="critical", ip="9.9.9.9", path="/v1/admin/x")
    files = list((tmp_path / "sec").glob("*.jsonl"))
    assert files and "auth.admin_rejected" in files[0].read_text(encoding="utf-8")
    assert snapshot().get("auth.admin_rejected", 0) >= 1
    assert any(r.get("event_type") == "auth.admin_rejected" for r in recent_alerts(limit=10))


def test_emit_identity_spoof_and_webhook_fail_alert(tmp_path, monkeypatch):
    monkeypatch.setenv("SECURITY_EVENTS_DIR", str(tmp_path / "sec"))
    from lumen.platform.security_events import emit
    from lumen.platform.security_alerts import recent_alerts
    from lumen.platform.security_metrics import snapshot

    emit("idor.identity_spoof", severity="critical", tenant_id="ten_a")
    emit("webhook.stripe_signature_failed", severity="critical", path="/v1/billing/webhook/stripe")
    emit("webhook.github_signature_failed", severity="critical", path="/v1/integrations/github/webhook")
    snap = snapshot()
    assert snap.get("idor.identity_spoof", 0) >= 1
    assert snap.get("webhook.stripe_signature_failed", 0) >= 1
    assert snap.get("webhook.github_signature_failed", 0) >= 1
    types = {r["event_type"] for r in recent_alerts(limit=20)}
    assert "idor.identity_spoof" in types
    assert "webhook.stripe_signature_failed" in types


def test_watched_events_cover_phase_e_requirements():
    from lumen.platform.security_alerts import WATCHED_EVENTS, should_alert

    for et in (
        "auth.admin_rejected",
        "idor.identity_spoof",
        "webhook.stripe_signature_failed",
        "webhook.github_signature_failed",
    ):
        assert et in WATCHED_EVENTS
        assert should_alert(et, "critical")


def test_rate_limiter_requires_redis_no_silent_fallback(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("JOB_REDIS_URL", raising=False)
    import lumen.platform.rate_limit as rl

    rl._LIMITER = None
    with patch("lumen.platform.runtime_config.redis_url", return_value=""):
        with pytest.raises(RuntimeError, match="REDIS_URL"):
            rl.RateLimiter()


def test_require_admin_fail_closed_when_limiter_raises(monkeypatch):
    pytest.importorskip("aiohttp")
    from aiohttp import web
    import lumen.api.auth as auth_mod

    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "phase-e-admin-token-32chars-long!!")
    req = MagicMock()
    req.headers = {"X-Admin-Token": "phase-e-admin-token-32chars-long!!"}
    req.path = "/v1/admin/credits/x/overview"
    req.remote = "10.0.0.1"
    with patch.object(auth_mod, "get_rate_limiter", side_effect=RuntimeError("redis_down")):
        with pytest.raises(web.HTTPException) as ei:
            auth_mod.require_admin(req)
        assert ei.value.status_code == 503


def test_admin_rejected_emit_on_bad_token(monkeypatch, tmp_path):
    pytest.importorskip("aiohttp")
    from aiohttp import web
    import lumen.api.auth as auth_mod
    from lumen.platform.security_metrics import snapshot, reset_for_tests

    reset_for_tests()
    monkeypatch.setenv("SECURITY_EVENTS_DIR", str(tmp_path / "sec"))
    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "correct-admin-token-32chars-xxxxx")

    class FakeLim:
        def allow(self, *a, **k):
            return True

        def remaining(self, *a, **k):
            return 5

        def seconds_until_allow(self, *a, **k):
            return 0

    req = MagicMock()
    req.headers = {"X-Admin-Token": "WRONG"}
    req.path = "/v1/admin/x"
    req.remote = "8.8.8.8"
    with patch.object(auth_mod, "get_rate_limiter", return_value=FakeLim()):
        with pytest.raises(web.HTTPException) as ei:
            auth_mod.require_admin(req)
        assert ei.value.status_code in (401, 403)
    assert snapshot().get("auth.admin_rejected", 0) >= 1


def test_path_traversal_rejected_by_firewall():
    fw = _load("lumen/api/request_firewall.py", "fw_pen")
    assert fw.path_is_rejected("/v1/jobs/../../etc/passwd") is True
    assert fw.path_is_rejected("/v1/hosts/..%2f..%2fetc/passwd") is True
    assert fw.path_is_rejected("/v1/me", "/v1/me?x=../secret") is True
    assert fw.path_is_rejected("/v1/jobs/job_abc") is False


def test_identity_spoof_raises_and_emits(monkeypatch, tmp_path):
    pytest.importorskip("aiohttp")
    from aiohttp import web
    from lumen.api.ownership import reject_identity_spoof
    from lumen.platform.security_metrics import snapshot, reset_for_tests

    reset_for_tests()
    monkeypatch.setenv("SECURITY_EVENTS_DIR", str(tmp_path / "sec"))
    with pytest.raises(web.HTTPException) as ei:
        reject_identity_spoof({"tenant_id": "ten_other"}, tenant_id="ten_mine")
    assert ei.value.status_code == 403
    assert snapshot().get("idor.identity_spoof", 0) >= 1


def test_job_routes_enforce_tenant_and_reject_dotdot():
    src = Path("lumen/api/routes/jobs.py").read_text(encoding="utf-8")
    assert "require_tenant" in src
    assert "tenant_id=tenant.tenant_id" in src
    assert '".." in job_id' in src or "in job_id" in src


def test_hosts_routes_tenant_scoped_and_spoof_reject():
    src = Path("lumen/api/routes/hosts.py").read_text(encoding="utf-8")
    assert "tenant_id=tenant.tenant_id" in src
    assert "reject_identity_spoof" in src
    assert "require_tenant" in src


def test_stripe_signature_verify_rejects_unsigned(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_phase_e_test_secret_value")
    from lumen.platform.stripe_client import verify_webhook_signature

    assert verify_webhook_signature(b'{"type":"x"}', "") is False
    assert verify_webhook_signature(b'{"type":"x"}', "t=1,v1=00") is False


def test_github_signature_logic_rejects_unsigned():
    import hashlib
    import hmac

    secret = "ghwh_secret_phase_e"

    def verify_signature(raw_body, signature_header):
        if not signature_header or not str(signature_header).startswith("sha256="):
            return False
        expected = str(signature_header).split("=", 1)[1].strip()
        digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, expected)

    assert verify_signature(b"{}", None) is False
    assert verify_signature(b"{}", "") is False
    dig = hmac.new(secret.encode(), b"{}", hashlib.sha256).hexdigest()
    assert verify_signature(b"{}", f"sha256={dig}") is True


def test_billing_and_github_routes_emit_on_sig_fail():
    billing = Path("lumen/api/routes/billing.py").read_text(encoding="utf-8")
    github = Path("lumen/api/routes/github_webhooks.py").read_text(encoding="utf-8")
    assert "webhook.stripe_signature_failed" in billing
    assert "webhook.github_signature_failed" in github


def test_dependabot_and_gitleaks_configs_present():
    dep = Path(".github/dependabot.yml").read_text(encoding="utf-8")
    assert 'package-ecosystem: "pip"' in dep
    assert "schedule:" in dep
    assert Path(".gitleaks.toml").is_file()
    sec = Path(".github/workflows/security.yml").read_text(encoding="utf-8")
    assert "gitleaks" in sec.lower()
    weekly = Path(".github/workflows/security-review-weekly.yml").read_text(encoding="utf-8")
    assert "gitleaks" in weekly.lower()
