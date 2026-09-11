"""Phase 4 — plan quota, repair, rate limits."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("TBE_ENV", "test")

from dataclasses import dataclass
from unittest.mock import patch

from lumen.hosting.serverless_policy import (
    assert_serverless_quota,
    count_serverless_running,
    max_serverless_bots,
    status_message_ar,
)
from lumen.hosting.serverless_repair import repair_serverless_project
from lumen.hosting.rate_limiter import max_concurrent


@dataclass
class _Inst:
    user_id: int
    sandbox_backend: str
    status: str


def test_max_serverless_free_vs_pro(monkeypatch):
    monkeypatch.setenv("TBE_SERVERLESS_MAX_FREE", "1")
    monkeypatch.setenv("TBE_SERVERLESS_MAX_PRO", "5")
    monkeypatch.delenv("TBE_USER_IS_PRO", raising=False)

    # Simulate entitlement plane unavailable → free cap
    with patch(
        "lumen.hosting.serverless_policy.resolve_plan_limits" if False else "builtins.__import__",
        side_effect=None,
    ):
        pass

    class FakeLimits:
        def __init__(self, is_pro, max_bots=50):
            self.is_pro = is_pro
            self.max_bots = max_bots

    def fake_import(name, *a, **k):
        if name == "lumen.bot.ui.pro_plan_entitlement" or name.endswith("pro_plan_entitlement"):
            import types
            m = types.ModuleType("lumen.bot.ui.pro_plan_entitlement")
            m.resolve_plan_limits = lambda uid: FakeLimits(False)
            return m
        return __import__(name, *a, **k)

    # Direct unit: patch at point of use via monkeypatch on module function
    import lumen.hosting.serverless_policy as pol

    def _free_path(uid):
        return FakeLimits(False)

    def _pro_path(uid):
        return FakeLimits(True)

    with patch.object(pol, "max_serverless_bots", wraps=pol.max_serverless_bots):
        # Inject by patching import inside function
        with patch.dict("sys.modules", {}):
            pass

    # Cleaner approach: patch the import target after creating stub module
    import sys
    import types
    mod = types.ModuleType("lumen.bot.ui.pro_plan_entitlement")
    mod.resolve_plan_limits = lambda uid: FakeLimits(False, 50)
    # Ensure parent packages exist as stubs if needed
    for pkg in ("lumen.bot", "lumen.bot.ui"):
        if pkg not in sys.modules:
            sys.modules[pkg] = types.ModuleType(pkg)
    sys.modules["lumen.bot.ui.pro_plan_entitlement"] = mod
    assert max_serverless_bots(1) == 1
    mod.resolve_plan_limits = lambda uid: FakeLimits(True, 50)
    assert max_serverless_bots(1) == 5


def test_assert_quota():
    with patch("lumen.hosting.serverless_policy.max_serverless_bots", return_value=1):
        ok, _ = assert_serverless_quota(user_id=1, running_serverless=0)
        assert ok
        ok2, msg = assert_serverless_quota(user_id=1, running_serverless=1)
        assert not ok2
        assert "استضافة" in msg or "حد" in msg


def test_count_serverless_running():
    items = [
        _Inst(1, "lumen_serverless", "running"),
        _Inst(1, "lumen_serverless", "stopped"),
        _Inst(1, "firecracker", "running"),
        _Inst(2, "lumen_serverless", "running"),
    ]
    assert count_serverless_running(items, user_id=1) == 1


def test_status_message_ar():
    assert "Lumen" in status_message_ar("RUNNING", verify_ok=True)
    assert "فشل" in status_message_ar("FAILED")


def test_max_concurrent_uses_plan(monkeypatch):
    import sys
    import types
    mod = types.ModuleType("lumen.bot.ui.pro_plan_entitlement")
    class Lim:
        max_bots = 3
        is_pro = False
    mod.resolve_plan_limits = lambda uid: Lim()
    for pkg in ("lumen.bot", "lumen.bot.ui"):
        if pkg not in sys.modules:
            sys.modules[pkg] = types.ModuleType(pkg)
    sys.modules["lumen.bot.ui.pro_plan_entitlement"] = mod
    monkeypatch.delenv("TBE_HOST_MAX_CONCURRENT_PER_USER", raising=False)
    assert max_concurrent(user_id=9) == 3


def test_repair_calls_adapt_and_start(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.setenv("LUMEN_SERVERLESS_SKIP_VERIFY", "1")
    monkeypatch.setenv("ENVIRONMENT", "test")
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('t').build()\n"
        "application.run_polling()\n",
        encoding="utf-8",
    )
    from lumen.engine.services.sandbox_runtime.types import SandboxHandle

    class FakeBackend:
        name = "lumen_serverless"

    with patch(
        "lumen.hosting.orchestration.start_host",
        return_value=(
            FakeBackend(),
            SandboxHandle(
                backend="lumen_serverless",
                deployment_id="dpl_r1",
                status="running",
                message="ok",
                meta={"url": "https://x.example", "verify_ok": True, "lifecycle_state": "RUNNING"},
            ),
        ),
    ):
        r = repair_serverless_project(tmp_path, bot_token="1:TOK", user_id=3)
    assert r.ok
    assert r.deployment_id == "dpl_r1"
    assert (tmp_path / "api" / "index.py").is_file()
