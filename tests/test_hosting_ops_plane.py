"""Hosting ops plane: secrets, rate limit, billing math, backup, orchestration."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_orchestration_is_fc_only() -> None:
    from lumen.engine.services.hosting import orchestration
    import inspect

    src = inspect.getsource(orchestration.start_host)
    assert "start_permanent_host_bot" in src


def test_secrets_seal_roundtrip(tmp_path: Path) -> None:
    from lumen.engine.services.hosting.secrets_env import (
        inject_secrets_env,
        load_project_secrets,
        seal_project_secrets,
    )

    (tmp_path / ".env").write_text("BOT_TOKEN=plain-secret-token-value\nFOO=1\n", encoding="utf-8")
    seal_project_secrets(tmp_path, {"BOT_TOKEN": "plain-secret-token-value"})
    sealed_file = tmp_path / ".lumen_secrets.sealed"
    assert sealed_file.is_file()
    assert "plain-secret" not in sealed_file.read_text(encoding="utf-8")
    env_txt = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "__SEALED__" in env_txt
    loaded = load_project_secrets(tmp_path)
    assert loaded.get("BOT_TOKEN") == "plain-secret-token-value"
    inj = inject_secrets_env(tmp_path, {"X": "1"})
    assert inj["BOT_TOKEN"] == "plain-secret-token-value"


def test_rate_limiter_blocks_excess(monkeypatch) -> None:
    monkeypatch.setenv("TBE_HOST_MAX_CONCURRENT_PER_USER", "2")
    monkeypatch.setenv("TBE_HOST_MAX_STARTS_PER_HOUR", "100")
    from lumen.engine.services.hosting.rate_limiter import check_can_start

    ok, _ = check_can_start(user_id=42, running_count=1)
    assert ok
    ok2, reason = check_can_start(user_id=42, running_count=2)
    assert not ok2
    assert "concurrent" in reason


def test_usage_billing_compute() -> None:
    from types import SimpleNamespace
    from lumen.engine.services.hosting.usage_billing import compute_credits, compute_session_usage
    import time

    inst = SimpleNamespace(
        instance_id="h1",
        user_id=1,
        project_path=".",
        started_at=time.time() - 600,
    )
    usage = compute_session_usage(inst)
    assert usage["host_minutes"] >= 9
    credits = compute_credits(usage)
    assert credits >= 0


def test_backup_manager_creates_tar(tmp_path: Path) -> None:
    (tmp_path / "bot.db").write_bytes(b"sqlite-bytes")
    from lumen.engine.services.hosting.backup_manager import backup_project

    r = backup_project(tmp_path, instance_id="testinst")
    assert r["ok"] is True
    assert Path(r["path"]).is_file()


def test_api_routes_host_ops_in_app() -> None:
    src = (REPO / "lumen/api/app.py").read_text(encoding="utf-8")
    assert "/v1/hosts/logs" in src
    assert "/v1/hosts/redeploy" in src
    assert "/v1/hosts/delete" in src


def test_service_wires_rate_and_secrets() -> None:
    src = (REPO / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "check_can_start" in src
    assert "seal_project_secrets" in src
    assert "settle_instance" in src
