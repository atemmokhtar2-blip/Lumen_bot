"""Security baseline — must stay green for world-class posture."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_security_baseline_script_strict():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts/security/security_baseline_check.py"), "--strict"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr


def test_admin_routes_call_require_admin():
    text = (ROOT / "lumen/api/routes/audit.py").read_text(encoding="utf-8")
    for fn in ("admin_tenant_overview", "admin_tenant_ledger", "admin_tenant_reconcile"):
        assert f"async def {fn}" in text
        # require_admin appears after def (same file uses it in each admin handler)
    assert text.count("require_admin") >= 3


def test_policy_engine_fail_closed_unknown_tool():
    from lumen.engine.security.policy import PolicyEngine, ToolRequest

    d = PolicyEngine().evaluate(ToolRequest(tool_name="not_a_real_tool_xyz", params={}))
    assert d.allowed is False
    assert "allowlist" in d.reason or "not" in d.reason.lower()


def test_policy_engine_known_tool_allowed():
    from lumen.engine.security.policy import PolicyEngine, ToolRequest

    d = PolicyEngine().evaluate(ToolRequest(tool_name="repo_understand", params={}))
    assert d.allowed is True


def test_policy_engine_sensitive_requires_confirm():
    from lumen.engine.security.policy import PolicyEngine, ToolRequest

    d = PolicyEngine().evaluate(ToolRequest(tool_name="git_push", params={}, confirmed=False))
    assert d.needs_confirmation is True


def test_security_headers_middleware_in_app_source():
    text = (ROOT / "lumen/api/app.py").read_text(encoding="utf-8")
    assert "security_headers_middleware" in text
    assert "Content-Security-Policy" in text
    assert "Strict-Transport-Security" in text


def test_credit_service_privilege_strings():
    text = (ROOT / "lumen.platform/credits/service.py").read_text(encoding="utf-8")
    for s in (
        "promotional_requires_expiry",
        "promotional_requires_promo_reason",
        "welcome_grant_key_required",
    ):
        assert s in text


def test_security_workflow_has_world_class_jobs():
    text = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    for needle in (
        "gitleaks",
        "pip-audit",
        "bandit",
        "semgrep",
        "codeql",
        "trivy",
        "scorecard",
        "credits_health_monitor",
        "security_baseline_check",
    ):
        assert needle in text.lower() or needle in text
