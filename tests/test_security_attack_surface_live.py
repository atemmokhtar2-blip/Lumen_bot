"""Offensive checks against real Lumen security gates (no network)."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _stub_aiohttp():
    if "aiohttp" not in sys.modules:
        import types
        m = types.ModuleType("aiohttp")
        m.web = types.SimpleNamespace(middleware=lambda f: f, Request=object, Response=object)
        sys.modules["aiohttp"] = m


def _load(name: str, rel: str):
    _stub_aiohttp()
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_run_shell_refuses_production_even_when_flag_on():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["TBE_MULTI_TENANT"] = "1"
    os.environ["CLINE_ALLOW_SHELL"] = "1"
    sys.path.insert(0, str(ROOT))
    from lumen.engine.services.cline_runtime.agent_fs import run_shell

    r = run_shell("/tmp", "ls")
    assert r.get("ok") is False
    assert "production" in r.get("error", "") or "shell_disabled" in r.get("error", "")


def test_run_shell_blocks_python_c_and_absolute_binary():
    os.environ["ENVIRONMENT"] = "development"
    os.environ["TBE_MULTI_TENANT"] = "0"
    os.environ["CLINE_ALLOW_SHELL"] = "1"
    sys.path.insert(0, str(ROOT))
    from lumen.engine.services.cline_runtime.agent_fs import run_shell

    assert run_shell("/tmp", 'python -c "print(1)"').get("ok") is False
    assert run_shell("/tmp", "/bin/ls").get("ok") is False


def test_local_process_refuses_multi_tenant():
    os.environ["ENVIRONMENT"] = "production"
    os.environ["TBE_MULTI_TENANT"] = "1"
    os.environ["TBE_ALLOW_LOCAL_PROCESS"] = "0"
    os.environ["TBE_FORCE_LOCAL_PROCESS"] = "0"
    sys.path.insert(0, str(ROOT))
    from lumen.engine.services.live_deployment.local_process_driver import LocalProcessDriver
    from lumen.engine.services.live_deployment.report_data import DEPLOY_FAILED

    st = LocalProcessDriver().deploy("/tmp/x", env_vars={"BOT_TOKEN": "0:x"}, service_name="t")
    assert st.status == DEPLOY_FAILED
    assert "local_process" in (st.message or "").lower() or "forbidden" in (st.message or "").lower()


def test_host_webhook_secret_const_time_and_prod_required():
    hw = _load("host_webhooks_under_test", "lumen/api/routes/host_webhooks.py")
    assert hw._const_eq("abc", "abc") is True
    assert hw._const_eq("abc", "abd") is False

    os.environ["ENVIRONMENT"] = "production"
    os.environ.pop("TBE_HOST_WEBHOOK_SECRET", None)

    class R:
        headers = {}

    assert hw._secret_ok(R(), "inst1") is False

    os.environ["TBE_HOST_WEBHOOK_SECRET"] = "super-secret-token-value"

    class R2:
        headers = {"X-Telegram-Bot-Api-Secret-Token": "super-secret-token-value"}

    assert hw._secret_ok(R2(), "inst1") is True

    class R3:
        headers = {"X-Telegram-Bot-Api-Secret-Token": "wrong"}

    assert hw._secret_ok(R3(), "inst1") is False


def test_safe_fs_blocks_traversal(tmp_path):
    sys.path.insert(0, str(ROOT))
    from lumen.engine.services.safe_fs import safe_resolve_under

    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(Exception):
        safe_resolve_under(root, "../etc/passwd")
    with pytest.raises(Exception):
        safe_resolve_under(root, "/etc/passwd")


def test_firewall_patterns():
    fw = _load("request_firewall_under_test", "lumen/api/request_firewall.py")
    assert fw._TRAVERSAL.search("/v1/jobs/../../etc/passwd")
    assert fw._PROBE.search("/v1/x?q=<script>alert(1)</script>")
    assert fw._PROBE.search("/v1/x?q=union select password from users")
