"""Phase 5 strong — preflight, pipeline, repair attach, session bindings."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from lumen.hosting.agent_host_pipeline import (
    attach_serverless_instance,
    format_instances_status,
    preflight_project,
    resolve_bot_token,
    resolve_project_path,
    run_host_pipeline,
)


@dataclass
class _Inst:
    instance_id: str = "i1"
    status: str = "running"
    sandbox_backend: str = "lumen_serverless"
    public_base_url: str = "https://x.example"
    webhook_public_url: str = "https://x.example/api"
    last_diagnosis: dict = field(default_factory=lambda: {"lifecycle_state": "RUNNING", "verify_ok": True})
    deployment_id: str = "dpl_1"
    last_error: str = ""


def test_resolve_project_path_from_active_repo(tmp_path):
    p = resolve_project_path(user_data={"active_repo": {"path": str(tmp_path)}})
    assert p == str(tmp_path.resolve())


def test_resolve_bot_token_sealed(tmp_path):
    with patch(
        "lumen.hosting.secrets_env.load_project_secrets",
        return_value={"BOT_TOKEN": "123:ABC"},
    ):
        assert resolve_bot_token(str(tmp_path)).startswith("123:")


def test_preflight_requires_python(tmp_path, monkeypatch):
    monkeypatch.delenv("TBE_HOST_BACKEND", raising=False)
    ok, msg, _ = preflight_project(str(tmp_path))
    assert not ok


def test_preflight_ok_with_main(tmp_path, monkeypatch):
    monkeypatch.delenv("TBE_HOST_BACKEND", raising=False)
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    ok, msg, d = preflight_project(str(tmp_path))
    assert ok
    assert d.get("entry_point") == "main.py"


def test_format_status_no_vendor():
    text = format_instances_status([_Inst()])
    assert "سريعة" in text
    assert "vercel" not in text.lower()


def test_pipeline_needs_project():
    r = run_host_pipeline(user_id=1, bot_token="1:T")
    assert not r.ok and r.data.get("needs_project")


def test_pipeline_success(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "firecracker")  # skip serverless prepare
    (tmp_path / "main.py").write_text("x", encoding="utf-8")
    inst = _Inst()
    host_result = MagicMock()
    host_result.ok = True
    host_result.instance = inst
    host_result.message = "ok"
    host_result.to_user_text = lambda: "البوت يعمل على استضافة Lumen."
    svc = MagicMock()
    svc.start.return_value = host_result
    svc.list_for_user.return_value = []
    with patch("lumen.hosting.agent_host_pipeline._hosting_service", return_value=svc):
        r = run_host_pipeline(user_id=7, project_path=str(tmp_path), bot_token="1:ABC")
    assert r.ok
    assert r.instance_id == "i1"
    assert r.lifecycle_state == "RUNNING"


def test_pipeline_repair_attaches_instance(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    (tmp_path / "main.py").write_text(
        "from telegram.ext import Application\n"
        "application = Application.builder().token('t').build()\n",
        encoding="utf-8",
    )
    host_result = MagicMock()
    host_result.ok = False
    host_result.instance = None
    host_result.message = "fail"
    host_result.to_user_text = lambda: "فشل"
    svc = MagicMock()
    svc.start.return_value = host_result
    svc.list_for_user.return_value = []
    svc._instances = {}
    svc._save = MagicMock()

    from lumen.hosting.serverless_repair import RepairResult

    with patch("lumen.hosting.agent_host_pipeline._hosting_service", return_value=svc), patch(
        "lumen.hosting.serverless_policy.count_serverless_running", return_value=0
    ), patch(
        "lumen.hosting.serverless_policy.assert_serverless_quota", return_value=(True, "ok")
    ), patch(
        "lumen.engine.services.hosting.prepare_runtime.prepare_project_for_serverless",
        return_value=MagicMock(ok=True, entry_point="main.py", details={}, message="ok"),
    ), patch(
        "lumen.hosting.serverless_repair.repair_serverless_project",
        return_value=RepairResult(
            ok=True,
            message="تم الإصلاح",
            deployment_id="dpl_r",
            url="https://fixed.example",
            meta={
                "lifecycle_state": "RUNNING",
                "verify_ok": True,
                "webhook_url": "https://fixed.example/api",
            },
        ),
    ), patch(
        "lumen.hosting.webhook_manager.apply_to_instance",
        return_value={"ok": True},
    ):
        r = run_host_pipeline(user_id=1, project_path=str(tmp_path), bot_token="1:T")
    assert r.ok
    assert r.data.get("repaired") is True
    assert r.deployment_id == "dpl_r"
    assert r.instance_id
    assert svc._save.called


def test_attach_serverless_instance_saves():
    svc = MagicMock()
    svc._instances = {}
    svc._save = MagicMock()
    with patch("lumen.hosting.webhook_manager.apply_to_instance", return_value={}):
        inst = attach_serverless_instance(
            svc,
            user_id=3,
            project_path="/p",
            bot_token="1:TOK",
            tenant_id="tg:3",
            deployment_id="d1",
            public_url="https://a.example",
            webhook_url="https://a.example/api",
            meta={"lifecycle_state": "RUNNING", "verify_ok": True},
        )
    assert inst.status == "running"
    assert inst.instance_id in svc._instances
