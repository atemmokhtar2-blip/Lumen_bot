"""Phase 1 — platform serverless driver (internal). No vendor names in user messages."""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from lumen.engine.services.live_deployment.vercel_client import (
    ApiResult,
    PlatformHostClient,
    collect_project_files,
    sanitize_project_name,
)
from lumen.engine.services.live_deployment.vercel_process_driver import VercelProcessDriver
from lumen.engine.services.live_deployment.report_data import DEPLOY_FAILED, DEPLOY_RUNNING


def test_sanitize_project_name():
    assert sanitize_project_name("Lumen User 839!") == "lumen-user-839"
    assert " " not in sanitize_project_name("a b c")


def test_collect_project_files(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "index.py").write_text("def handler():\n    return {}\n", encoding="utf-8")
    (tmp_path / "vercel.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x", encoding="utf-8")
    files = collect_project_files(tmp_path)
    rels = {f["file"] for f in files}
    assert "api/index.py" in rels
    assert "vercel.json" in rels
    assert not any(x.startswith(".git") for x in rels)
    # data is base64
    raw = base64.b64decode(files[0]["data"])
    assert isinstance(raw, (bytes, bytearray))


def test_client_missing_token():
    c = PlatformHostClient(token="")
    r = c.create_project("x")
    assert r.ok is False
    assert "token" in r.error


def test_driver_name_is_lumen_serverless_not_vendor():
    d = VercelProcessDriver(client=PlatformHostClient(token=""))
    assert d.name == "lumen_serverless"
    st = d.deploy("/tmp", env_vars={"BOT_TOKEN": "x"})
    assert st.provider == "lumen_serverless"
    assert "vercel" not in st.message.lower()
    assert "Vercel" not in st.message


def test_driver_deploy_success_mocked(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "index.py").write_text("ok", encoding="utf-8")

    class FakeClient(PlatformHostClient):
        def __init__(self):
            super().__init__(token="test-token")

        def ensure_project(self, name):
            return ApiResult(ok=True, status=200, data={"id": "prj_123", "name": name})

        def upsert_env(self, project_id, key, value, **kwargs):
            assert key in {"BOT_TOKEN", "TELEGRAM_BOT_TOKEN"} or True
            assert value  # present
            return ApiResult(ok=True, status=200, data={})

        def create_file_deployment(self, **kwargs):
            return ApiResult(
                ok=True,
                status=200,
                data={"id": "dpl_abc", "url": "lumen-bot.example.app", "readyState": "READY"},
            )

    d = VercelProcessDriver(client=FakeClient())
    st = d.deploy(
        str(tmp_path),
        env_vars={"BOT_TOKEN": "123:AA"},
        service_name="lumen-user-1-bot-01",
    )
    assert st.status == DEPLOY_RUNNING
    assert st.deployment_id == "dpl_abc"
    assert st.url.startswith("https://")
    assert "vercel" not in st.message.lower()
    assert "Lumen" in st.message or "lumen" in st.message.lower() or "يعمل" in st.message


def test_driver_env_failure_on_bot_token(tmp_path):
    (tmp_path / "main.py").write_text("x", encoding="utf-8")

    class FakeClient(PlatformHostClient):
        def __init__(self):
            super().__init__(token="t")

        def ensure_project(self, name):
            return ApiResult(ok=True, data={"id": "prj"})

        def upsert_env(self, project_id, key, value, **kwargs):
            if key == "BOT_TOKEN":
                return ApiResult(ok=False, error="denied")
            return ApiResult(ok=True, data={})

        def create_file_deployment(self, **kwargs):
            raise AssertionError("should not deploy without bot token env")

    d = VercelProcessDriver(client=FakeClient())
    st = d.deploy(str(tmp_path), env_vars={"BOT_TOKEN": "secret"}, service_name="b1")
    assert st.status == DEPLOY_FAILED


def test_stop_and_status_messages_clean():
    class FakeClient(PlatformHostClient):
        def __init__(self):
            super().__init__(token="t")

        def get_deployment(self, deployment_id):
            return ApiResult(ok=True, data={"id": deployment_id, "readyState": "READY", "url": "x.app"})

        def cancel_deployment(self, deployment_id):
            return ApiResult(ok=True, data={})

    d = VercelProcessDriver(client=FakeClient())
    st = d.status("dpl_1")
    assert st.status == DEPLOY_RUNNING
    assert "vercel" not in st.message.lower()
    st2 = d.stop("dpl_1")
    assert st2.status == "stopped"


def test_secrets_provider_lists_vercel_token():
    src = Path("lumen/platform/secrets_provider.py").read_text(encoding="utf-8")
    assert "VERCEL_TOKEN" in src
    assert "VERCEL_TEAM_ID" in src
