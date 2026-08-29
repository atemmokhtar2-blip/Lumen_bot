"""Security hardening v1 — verifies all 7 vulnerability fixes from the root."""
from __future__ import annotations

import os
import re
import tempfile
import zipfile
from pathlib import Path

import pytest

# ── Vuln #1: No shared fallback in user isolation ──────────────────────

def test_vuln1_git_router_no_shared_clones_fallback():
    src = Path("lumen/bot/routers/git_router.py").read_text()
    assert 'Path(OUTPUT_DIR) / "clones"' not in src, \
        "git_router still has shared clones fallback (Vuln #1)"
    assert "SandboxUnavailable" in src, "git_router must define SandboxUnavailable"
    assert "raise SandboxUnavailable" in src, "_dest_for must raise on failure"

def test_vuln1_token_handler_no_shared_clones_fallback():
    src = Path("lumen/bot/handlers/token_handler.py").read_text()
    assert 'Path(OUTPUT_DIR) / "clones"' not in src, \
        "token_handler still has shared clones fallback (Vuln #1)"

def test_vuln1_no_shared_clones_anywhere_in_lumen():
    import subprocess
    result = subprocess.run(
        ["grep", "-rl", 'OUTPUT_DIR) / "clones"', "lumen/"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0 or not result.stdout.strip(), \
        f"Shared clones fallback found in: {result.stdout}"

# ── Vuln #2: Dual-bucket rate limit (IP + identity) ────────────────────

def test_vuln2_dual_bucket_ip_always_checked():
    src = Path("lumen/api/app.py").read_text()
    assert "ip_key" in src, "Must use ip_key (not replace key)"
    assert "identity_key" in src, "Must use identity_key for second bucket"
    old_tenant = re.search(r'^\s*key = f"tenant:', src, re.MULTILINE)
    old_auth = re.search(r'^\s*key = f"auth:', src, re.MULTILINE)
    assert not old_tenant, "Old vulnerable key-replacement (tenant) still present (Vuln #2)"
    assert not old_auth, "Old vulnerable key-replacement (auth) still present (Vuln #2)"

def test_vuln2_ip_checked_before_identity():
    src = Path("lumen/api/app.py").read_text()
    ip_pos = src.find('ip_key = f"ip:{ip}"')
    identity_pos = src.find("identity_key")
    assert ip_pos >= 0, "ip_key assignment not found"
    assert identity_pos >= 0, "identity_key not found"
    assert ip_pos < identity_pos, "IP bucket must be checked before identity bucket"

# ── Vuln #3: Path injection — strict validation before git ops ─────────

def test_vuln3_git_router_validates_path_before_push_pull():
    src = Path("lumen/bot/routers/git_router.py").read_text()
    assert "_validate_user_path" in src, "Must have _validate_user_path helper"
    assert "validate_user_project_path" in src, \
        "Must reuse validate_user_project_path from security module"
    assert src.count("_validate_user_path") >= 3, \
        "Must call _validate_user_path in push + pull + definition"

def test_vuln3_token_handler_validates_path_before_host_and_push():
    src = Path("lumen/bot/handlers/token_handler.py").read_text()
    assert "validate_user_project_path" in src, \
        "Must call validate_user_project_path"
    assert src.count("validate_user_project_path") >= 2, \
        "Must validate before svc.start AND git_push"

# ── Vuln #4: ZIP excludes ALL dotfiles ─────────────────────────────────

def test_vuln4_safe_zip_excludes_all_dotfiles():
    src = Path("lumen/engine/services/safe_zip.py").read_text()
    assert 'name.startswith(".")' in src, \
        "Must skip ALL dotfiles by prefix, not just a fixed list"

def test_vuln4_safe_zip_functional_dotfile_exclusion():
    from lumen.engine.services.safe_zip import write_project_zip
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        (root / ".env").write_text("SECRET=leaked")
        (root / ".env.staging").write_text("STAGING=leaked")
        (root / ".aws").mkdir()
        (root / ".aws" / "credentials").write_text("aws_secret=leaked")
        (root / ".npmrc").write_text("authToken=leaked")
        (root / "main.py").write_text("print('hello')")
        (root / "README.md").write_text("# project")
        out = write_project_zip(root, root.parent / "out.zip")
        assert out is not None, "zip creation failed"
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            leaked = [n for n in names if n.startswith(".")]
            assert not leaked, f"Dotfiles leaked into zip: {leaked}"
            assert "main.py" in names
            assert "README.md" in names

# ── Vuln #5: SSRF — DNS resolution + private IP block ──────────────────

def test_vuln5_secure_exec_has_dns_resolution():
    src = Path("lumen/engine/services/secure_exec.py").read_text()
    assert "import socket" in src or "from socket" in src, \
        "Must import socket for DNS resolution"
    assert "getaddrinfo" in src, "Must use getaddrinfo for DNS resolution"
    assert "ipaddress" in src, "Must import ipaddress for IP validation"
    assert "is_global" in src, "Must check ip.is_global (blocks private/metadata)"
    assert "_assert_host_resolves_to_public" in src, \
        "Must have _assert_host_resolves_to_public function"

def test_vuln5_blocks_private_and_metadata_ips():
    from lumen.engine.services.secure_exec import _assert_host_resolves_to_public
    bad_ips = [
        "169.254.169.254", "127.0.0.1", "10.0.0.1",
        "172.16.0.1", "192.168.1.1", "0.0.0.0",
    ]
    for ip in bad_ips:
        with pytest.raises(ValueError, match="git_host_private_ip|git_host_bad_ip"):
            _assert_host_resolves_to_public(ip)

def test_vuln5_blocks_unresolvable_host():
    from lumen.engine.services.secure_exec import _assert_host_resolves_to_public
    with pytest.raises(ValueError, match="git_host_dns_unresolvable|git_host_no_dns"):
        _assert_host_resolves_to_public("this-does-not-exist-xyz-abc.invalid")

def test_vuln5_allows_public_github():
    from lumen.engine.services.secure_exec import validate_git_https_url
    result = validate_git_https_url("https://github.com/octocat/Hello-World.git")
    assert result == "https://github.com/octocat/Hello-World.git"

# ── Vuln #6: Fail-closed secrets in production ─────────────────────────

def test_vuln6_secrets_required_defaults_to_closed_in_production(monkeypatch):
    for k in ["ENVIRONMENT", "TBE_ENV", "SECRETS_REQUIRED",
              "KUBERNETES_SERVICE_HOST", "RAILWAY_ENVIRONMENT", "FORCE_PRODUCTION"]:
        monkeypatch.delenv(k, raising=False)
    from lumen.platform.secrets_provider import _required, _is_dev_environment
    assert not _is_dev_environment(), "No dev signals -> production"
    assert _required() is True, "Production must default to fail-closed"

def test_vuln6_production_ignores_secrets_required_zero(monkeypatch):
    for k in ["ENVIRONMENT", "TBE_ENV", "KUBERNETES_SERVICE_HOST",
              "RAILWAY_ENVIRONMENT", "FORCE_PRODUCTION"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SECRETS_REQUIRED", "0")
    from lumen.platform.secrets_provider import _required
    assert _required() is True, "Production must ignore SECRETS_REQUIRED=0"

def test_vuln6_dev_allows_fail_open_with_explicit_zero(monkeypatch):
    for k in ["KUBERNETES_SERVICE_HOST", "RAILWAY_ENVIRONMENT", "FORCE_PRODUCTION"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("SECRETS_REQUIRED", "0")
    from lumen.platform.secrets_provider import _required, _is_dev_environment
    assert _is_dev_environment() is True
    assert _required() is False, "Dev with explicit 0 may fail-open"

def test_vuln6_production_signals_override_dev_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    for k in ["SECRETS_REQUIRED", "FORCE_PRODUCTION"]:
        monkeypatch.delenv(k, raising=False)
    from lumen.platform.secrets_provider import _is_dev_environment, _required
    assert not _is_dev_environment(), "K8s signal overrides ENVIRONMENT=dev"
    assert _required() is True, "Production signals -> fail-closed"

# ── Vuln #7: IDOR — reject_identity_spoof on all body-accepting endpoints ─

def test_vuln7_usage_routes_have_identity_spoof_check():
    src = Path("lumen/api/routes/usage.py").read_text()
    assert "reject_identity_spoof" in src, \
        "usage.py must call reject_identity_spoof (Vuln #7)"
    assert src.count("reject_identity_spoof") >= 2, \
        "Both post_batch and register_bot_route need reject_identity_spoof"

def test_vuln7_billing_dev_activate_has_identity_spoof_check():
    src = Path("lumen/api/routes/billing.py").read_text()
    assert "reject_identity_spoof" in src
    dev_pos = src.find("async def dev_activate")
    if dev_pos >= 0:
        section = src[dev_pos:]
        assert "reject_identity_spoof" in section, \
            "dev_activate must call reject_identity_spoof"

def test_vuln7_all_body_routes_have_spoof_protection():
    routes_dir = Path("lumen/api/routes")
    for fpath in sorted(routes_dir.glob("*.py")):
        content = fpath.read_text()
        has_body = bool(re.search(r"json_body|safe_json_body|body\.get|request\.json", content))
        if not has_body:
            continue
        if fpath.name == "health.py":
            continue
        has_spoof = "reject_identity_spoof" in content
        has_pop = 'body.pop("tenant_id"' in content or 'pop("tenant_id"' in content
        has_ownership = "assert_job_owned" in content or "assert_host_owned" in content
        reads_identity = bool(re.search(
            r'body\.get\(\s*["\'](?:tenant_id|tenant|user_id|owner_id|account_id|org_id)["\']',
            content,
        ))
        assert has_spoof or has_pop or (has_ownership and not reads_identity), \
            f"{fpath.name}: accepts body but has no identity-spoof protection " \
            f"and reads identity fields from body"
