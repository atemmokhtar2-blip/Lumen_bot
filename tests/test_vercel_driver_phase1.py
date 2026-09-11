"""Phase 1 — real platform-host protocol (upload digest → deploy sha → wait)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from lumen.engine.services.live_deployment.report_data import DEPLOY_FAILED, DEPLOY_RUNNING
from lumen.engine.services.live_deployment.vercel_client import (
    ApiResult,
    LocalFile,
    PlatformHostClient,
    collect_local_files,
    collect_project_files,
    sanitize_project_name,
    sha1_bytes,
)
from lumen.engine.services.live_deployment.vercel_process_driver import VercelProcessDriver


def test_sanitize_and_sha():
    assert sanitize_project_name("Lumen User!!") == "lumen-user"
    assert sha1_bytes(b"abc") == hashlib.sha1(b"abc").hexdigest()


def test_collect_local_files_skips_git(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "index.py").write_text("def h():\n    pass\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "x").write_text("no", encoding="utf-8")
    files = collect_local_files(tmp_path)
    assert any(f.rel == "api/index.py" for f in files)
    assert not any(".git" in f.rel for f in files)
    # back-compat dict form includes sha
    dicts = collect_project_files(tmp_path)
    assert dicts[0]["sha"] == sha1_bytes(Path(tmp_path, dicts[0]["file"]).read_bytes())


def test_upload_file_sends_digest_header():
    seen = {}

    class C(PlatformHostClient):
        def __init__(self):
            super().__init__(token="tok")

        def request_raw(self, method, path, *, raw, headers, query=None):
            seen["method"] = method
            seen["path"] = path
            seen["digest"] = headers.get("x-vercel-digest")
            seen["len"] = headers.get("Content-Length")
            seen["body_len"] = len(raw)
            return ApiResult(ok=True, status=200, data={})

    c = C()
    content = b"hello-lumen"
    r = c.upload_file(content)
    assert r.ok
    assert seen["path"] == "/v2/files"
    assert seen["digest"] == sha1_bytes(content)
    assert seen["body_len"] == len(content)


def test_create_deployment_uses_sha_size_refs():
    bodies = []

    class C(PlatformHostClient):
        def __init__(self):
            super().__init__(token="tok")

        def upload_local_files(self, files):
            return ApiResult(ok=True, status=200, data={})

        def request_json(self, method, path, *, body=None, query=None):
            bodies.append(body)
            return ApiResult(ok=True, status=200, data={"id": "dpl_1", "readyState": "QUEUED", "url": "x.app"})

    f = LocalFile(rel="api/index.py", content=b"print(1)")
    r = C().create_deployment_from_files(project_name="lumen-bot", files=[f])
    assert r.ok
    files = bodies[0]["files"]
    assert files[0]["file"] == "api/index.py"
    assert files[0]["sha"] == f.sha
    assert files[0]["size"] == f.size
    assert "encoding" not in files[0]  # uploaded ref shape


def test_inline_deployment_has_encoding_base64():
    bodies = []

    class C(PlatformHostClient):
        def __init__(self):
            super().__init__(token="tok")

        def request_json(self, method, path, *, body=None, query=None):
            bodies.append(body)
            return ApiResult(ok=True, data={"id": "dpl_2", "readyState": "READY", "url": "y.app"})

    f = LocalFile(rel="a.py", content=b"x=1")
    C().create_inline_deployment(project_name="n", files=[f])
    item = bodies[0]["files"][0]
    assert item["encoding"] == "base64"
    assert item["file"] == "a.py"
    assert item["data"]


def test_driver_messages_have_no_vendor_name(tmp_path):
    (tmp_path / "m.py").write_text("x", encoding="utf-8")
    d = VercelProcessDriver(client=PlatformHostClient(token=""))
    st = d.deploy(str(tmp_path))
    assert st.provider == "lumen_serverless"
    assert "vercel" not in st.message.lower()


def test_driver_full_success_path(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "index.py").write_text("ok", encoding="utf-8")

    class Fake(PlatformHostClient):
        def __init__(self):
            super().__init__(token="tok")

        def ensure_project(self, name):
            return ApiResult(ok=True, data={"id": "prj_1", "name": name})

        def upsert_env(self, project_id_or_name, key, value, **kwargs):
            assert kwargs.get("encrypted") is True or key == "BOT_TOKEN"
            return ApiResult(ok=True, data={})

        def create_deployment_from_files(self, **kwargs):
            return ApiResult(ok=True, data={"id": "dpl_ok", "url": "app.example", "readyState": "QUEUED"})

        def wait_ready(self, deployment_id, **kwargs):
            return ApiResult(
                ok=True,
                data={"id": deployment_id, "url": "app.example", "readyState": "READY", "projectId": "prj_1"},
            )

    st = VercelProcessDriver(client=Fake()).deploy(
        str(tmp_path), env_vars={"BOT_TOKEN": "1:AA"}, service_name="lumen-u1-b1"
    )
    assert st.status == DEPLOY_RUNNING
    assert st.deployment_id == "dpl_ok"
    assert st.url.startswith("https://")
    assert "vercel" not in st.message.lower()


def test_driver_token_env_failure(tmp_path):
    (tmp_path / "x.py").write_text("1", encoding="utf-8")

    class Fake(PlatformHostClient):
        def __init__(self):
            super().__init__(token="tok")

        def ensure_project(self, name):
            return ApiResult(ok=True, data={"id": "p"})

        def upsert_env(self, *a, **k):
            return ApiResult(ok=False, error="no")

        def create_deployment_from_files(self, **kwargs):
            raise AssertionError("must not deploy")

    st = VercelProcessDriver(client=Fake()).deploy(str(tmp_path), env_vars={"BOT_TOKEN": "t"})
    assert st.status == DEPLOY_FAILED


def test_stop_deletes_deployment():
    calls = []

    class Fake(PlatformHostClient):
        def __init__(self):
            super().__init__(token="tok")

        def delete_deployment(self, deployment_id):
            calls.append(("delete", deployment_id))
            return ApiResult(ok=True, data={"state": "DELETED"})

        def cancel_deployment(self, deployment_id):
            calls.append(("cancel", deployment_id))
            return ApiResult(ok=True, data={})

    st = VercelProcessDriver(client=Fake()).stop("dpl_xyz")
    assert st.status == "stopped"
    assert calls[0] == ("delete", "dpl_xyz")


def test_secrets_managed_keys():
    src = Path("lumen/platform/secrets_provider.py").read_text(encoding="utf-8")
    assert "VERCEL_TOKEN" in src
