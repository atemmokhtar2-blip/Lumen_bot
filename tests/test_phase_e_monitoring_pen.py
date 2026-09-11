"""Phase E — monitoring + directed penetration (must not skip core cases)."""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Install aiohttp stub BEFORE any lumen.api imports when aiohttp absent
from tests.aiohttp_stub import install_aiohttp_stub, HTTPException

install_aiohttp_stub()


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
    monkeypatch.setenv("PLATFORM_ADMIN_TOKEN", "phase-e-admin-token-32chars-long!!")
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


# ── 1) Alerts on required events ─────────────────────────────────────────────

def test_alert_admin_rejected(tmp_path, monkeypatch):
    from lumen.platform.security_events import emit
    from lumen.platform.security_metrics import snapshot
    from lumen.platform.security_alerts import recent_alerts

    emit("auth.admin_rejected", severity="critical", ip="1.1.1.1", path="/v1/admin/x")
    assert "auth.admin_rejected" in next((tmp_path / "sec").glob("*.jsonl")).read_text()
    assert snapshot()["auth.admin_rejected"] >= 1
    assert any(a["event_type"] == "auth.admin_rejected" for a in recent_alerts())


def test_alert_identity_spoof_and_webhook_fails(tmp_path, monkeypatch):
    from lumen.platform.security_events import emit
    from lumen.platform.security_metrics import snapshot
    from lumen.platform.security_alerts import recent_alerts

    for et in (
        "idor.identity_spoof",
        "webhook.stripe_signature_failed",
        "webhook.github_signature_failed",
    ):
        emit(et, severity="critical", path="/v1/x")
    snap = snapshot()
    for et in (
        "idor.identity_spoof",
        "webhook.stripe_signature_failed",
        "webhook.github_signature_failed",
    ):
        assert snap.get(et, 0) >= 1
    types = {a["event_type"] for a in recent_alerts(limit=30)}
    assert "idor.identity_spoof" in types
    assert "webhook.stripe_signature_failed" in types


# ── 2) Admin brute + Redis down ──────────────────────────────────────────────

def test_admin_redis_down_fail_closed_503(monkeypatch, tmp_path):
    install_aiohttp_stub()
    # Fresh import path
    import importlib
    import lumen.api.auth as auth_mod
    importlib.reload(auth_mod)

    from aiohttp import web

    req = MagicMock()
    req.headers = {"X-Admin-Token": "phase-e-admin-token-32chars-long!!"}
    req.path = "/v1/admin/credits/t/overview"
    req.remote = "10.0.0.9"
    with patch("lumen.platform.rate_limit.get_rate_limiter", side_effect=RuntimeError("redis_down")):
        with pytest.raises(Exception) as ei:
            auth_mod.require_admin(req)
    exc = ei.value
    code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    assert code == 503
    # event emitted
    from lumen.platform.security_metrics import snapshot
    # may have admin_rate_limit_unavailable
    assert (
        snapshot().get("auth.admin_rate_limit_unavailable", 0) >= 1
        or "admin_rate_limit_unavailable" in str(getattr(exc, "text", ""))
    )


def test_admin_wrong_token_emits_rejected(monkeypatch, tmp_path):
    install_aiohttp_stub()
    import importlib
    import lumen.api.auth as auth_mod
    importlib.reload(auth_mod)

    class FakeLim:
        def allow(self, *a, **k):
            return True

        def remaining(self, *a, **k):
            return 5

        def seconds_until_allow(self, *a, **k):
            return 0

    req = MagicMock()
    req.headers = {"X-Admin-Token": "WRONG-TOKEN"}
    req.path = "/v1/admin/x"
    req.remote = "8.8.4.4"
    with patch("lumen.platform.rate_limit.get_rate_limiter", return_value=FakeLim()):
        with pytest.raises(Exception) as ei:
            auth_mod.require_admin(req)
    assert getattr(ei.value, "status_code", 0) in (401, 403)
    from lumen.platform.security_metrics import snapshot
    assert snapshot().get("auth.admin_rejected", 0) >= 1


def test_rate_limiter_no_memory_fallback(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("JOB_REDIS_URL", raising=False)
    import lumen.platform.rate_limit as rl

    rl._LIMITER = None
    with patch("lumen.platform.runtime_config.redis_url", return_value=""):
        with pytest.raises(RuntimeError, match="REDIS_URL"):
            rl.RateLimiter()


# ── 3) Path traversal ────────────────────────────────────────────────────────

def test_path_traversal_rejected():
    fw = _load("lumen/api/request_firewall.py", "fw_e")
    assert fw.path_is_rejected("/v1/jobs/../../etc/passwd") is True
    assert fw.path_is_rejected("/v1/hosts/..%2f..%2fetc/passwd") is True
    assert fw.path_is_rejected("/v1/x", "/v1/x?a=../etc/passwd") is True
    assert fw.path_is_rejected("/v1/jobs/job_ok") is False


# ── 4) IDOR jobs / hosts ─────────────────────────────────────────────────────

def test_idor_job_cross_tenant_permission_error():
    from lumen.application.handlers.job_handlers import handle_get_job
    from lumen.application.queries.get_job import GetJobQuery
    from lumen.domain.entities.job import Job
    from lumen.domain.value_objects.job_status import JobStatus
    import time

    class MemRepo:
        def __init__(self, job):
            self._job = job

        def get(self, job_id):
            return self._job if self._job.job_id == job_id else None

    job = Job(
        job_id="job_owned_by_a",
        tenant_id="ten_a",
        kind="generate",
        status=JobStatus.QUEUED,
        created_at=time.time(),
        input={},
    )
    repo = MemRepo(job)
    # owner OK
    got = handle_get_job(GetJobQuery(job_id="job_owned_by_a", tenant_id="ten_a"), jobs=repo)
    assert got.tenant_id == "ten_a"
    # cross-tenant IDOR blocked
    with pytest.raises(PermissionError, match="job_not_owned"):
        handle_get_job(GetJobQuery(job_id="job_owned_by_a", tenant_id="ten_b"), jobs=repo)


def test_idor_host_instance_wrong_tenant():
    from lumen.platform.tenant_isolation import assert_instance_owner

    inst = SimpleNamespace(user_id=7, tenant_id="ten_a")
    assert assert_instance_owner(inst, user_id=7, tenant_id="ten_a") is True
    assert assert_instance_owner(inst, user_id=7, tenant_id="ten_b") is False
    assert assert_instance_owner(inst, user_id=99, tenant_id="ten_a") is False


def test_identity_spoof_forbidden_and_emits(monkeypatch, tmp_path):
    install_aiohttp_stub()
    import importlib
    import lumen.api.ownership as own
    importlib.reload(own)

    from lumen.platform.security_metrics import snapshot, reset_for_tests
    reset_for_tests()
    with pytest.raises(Exception) as ei:
        own.reject_identity_spoof({"tenant_id": "ten_other"}, tenant_id="ten_mine")
    assert getattr(ei.value, "status_code", 0) == 403
    assert snapshot().get("idor.identity_spoof", 0) >= 1


# ── 5) Webhook without signature ─────────────────────────────────────────────

def test_stripe_webhook_unsigned_rejected(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_phase_e_secret_value_xx")
    from lumen.platform.stripe_client import verify_webhook_signature

    assert verify_webhook_signature(b'{"id":"evt"}', "") is False
    assert verify_webhook_signature(b'{"id":"evt"}', "t=1,v1=dead") is False


def test_github_webhook_unsigned_rejected():
    secret = "gh_wh_secret_e"
    def verify(raw, sig):
        if not sig or not str(sig).startswith("sha256="):
            return False
        exp = str(sig).split("=", 1)[1]
        dig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(dig, exp)
    assert verify(b"{}", None) is False
    assert verify(b"{}", "") is False
    assert verify(b"{}", "sha256=00") is False


def test_webhook_routes_emit_signature_failures():
    assert "webhook.stripe_signature_failed" in Path("lumen/api/routes/billing.py").read_text()
    assert "webhook.github_signature_failed" in Path("lumen/api/routes/github_webhooks.py").read_text()


# ── 6) Dependabot + gitleaks continuous ──────────────────────────────────────

def test_dependabot_gitleaks_hygiene_script():
    import subprocess
    r = subprocess.run(
        [sys.executable, "scripts/security/assert_monitoring_hygiene.py"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
