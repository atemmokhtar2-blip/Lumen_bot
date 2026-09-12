"""HostService real fail-closed for serverless + no NameError on failed start."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch


@dataclass
class _Handle:
    backend: str = "lumen_serverless"
    deployment_id: str = "dpl_x"
    status: str = "running"
    message: str = "ok"
    meta: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {"running", "starting"} and bool(self.deployment_id)


@dataclass
class _Backend:
    name: str = "lumen_serverless"


def _project_in_sandbox(tmp_path: Path, user_id: int = 1) -> Path:
    from lumen.engine.services.user_sandbox import get_user_sandbox
    sb = get_user_sandbox(user_id, tmp_path)
    root = Path(sb.root) if not isinstance(sb.root, Path) else sb.root
    proj = root / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "main.py").write_text("print(1)\n", encoding="utf-8")
    return proj


def test_serverless_running_without_verify_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    proj = _project_in_sandbox(tmp_path)

    handle = _Handle(
        status="running",
        meta={"url": "https://x.example", "verify_ok": False, "lifecycle_state": "FAILED"},
    )
    with patch(
        "lumen.engine.services.hosting.market_gate.evaluate_market_gate",
        return_value=MagicMock(ok=True, message_ar=lambda: "ok"),
    ), patch(
        "lumen.engine.services.hosting.prepare_runtime.prepare_project_for_serverless",
        return_value=MagicMock(ok=True, entry_point="main.py", details={}, env_vars={}),
    ), patch(
        "lumen.engine.services.live_deployment.token_validator.TokenValidator"
    ) as TV, patch(
        "lumen.hosting.orchestration.start_host",
        return_value=(_Backend(), handle),
    ), patch(
        "lumen.hosting.secrets_env.seal_project_secrets"
    ), patch(
        "lumen.hosting.secrets_env.inject_secrets_env",
        side_effect=lambda path, env: env,
    ), patch(
        "lumen.platform.tenant_isolation.verify_project_under_owner",
        side_effect=lambda path, **kw: str(path),
    ):
        TV.return_value.validate.return_value = MagicMock(valid=True, bot_username="b")
        from lumen.engine.services.hosting.service import HostingService
        svc = HostingService(state_dir=tmp_path / "state")
        res = svc.start(
            user_id=1,
            project_path=str(proj),
            bot_token="123456:ABCDEF-fake",
            tenant_id="tg:1",
        )
    assert res.ok is False
    msg = res.message or ""
    assert any(x in msg for x in ("تحقق", "verify", "مرفوض", "فشل", "عزل")) or res.ok is False


def test_failed_start_no_nameerror(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_HOST_BACKEND", "lumen_serverless")
    monkeypatch.setenv("TBE_MULTI_TENANT", "0")
    proj = _project_in_sandbox(tmp_path)
    handle = _Handle(status="failed", deployment_id="dpl_f", meta={"url": "", "verify_ok": False})
    with patch(
        "lumen.engine.services.hosting.market_gate.evaluate_market_gate",
        return_value=MagicMock(ok=True, message_ar=lambda: "ok"),
    ), patch(
        "lumen.engine.services.hosting.prepare_runtime.prepare_project_for_serverless",
        return_value=MagicMock(ok=True, entry_point="main.py", details={}, env_vars={}),
    ), patch(
        "lumen.engine.services.live_deployment.token_validator.TokenValidator"
    ) as TV, patch(
        "lumen.hosting.orchestration.start_host",
        return_value=(_Backend(), handle),
    ), patch(
        "lumen.hosting.secrets_env.seal_project_secrets"
    ), patch(
        "lumen.hosting.secrets_env.inject_secrets_env",
        side_effect=lambda path, env: env,
    ), patch(
        "lumen.platform.tenant_isolation.verify_project_under_owner",
        side_effect=lambda path, **kw: str(path),
    ):
        TV.return_value.validate.return_value = MagicMock(valid=True, bot_username="b")
        from lumen.engine.services.hosting.service import HostingService
        svc = HostingService(state_dir=tmp_path / "state2")
        res = svc.start(
            user_id=1,
            project_path=str(proj),
            bot_token="123456:ABCDEF-fake",
            tenant_id="tg:1",
        )
    assert res.ok is False
