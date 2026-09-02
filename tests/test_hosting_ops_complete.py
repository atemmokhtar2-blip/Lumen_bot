
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]

def test_orchestration_resolves_fc_by_default():
    from lumen.engine.services.hosting.orchestration import resolve_backend_name
    assert resolve_backend_name(project_path="/tmp") == "firecracker"

def test_orchestration_rejects_docker_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_MULTI_TENANT", "1")
    monkeypatch.delenv("TBE_HOST_ALLOW_WEAK_BACKEND", raising=False)
    from lumen.engine.services.hosting.orchestration import resolve_backend_name
    import pytest
    with pytest.raises(RuntimeError):
        resolve_backend_name(requested="docker")

def test_lumen_hosting_package_imports():
    import lumen.hosting as h
    assert callable(h.start_host)
    assert callable(h.backup_project)
    assert callable(h.check_can_start)

def test_ops_scheduler_module():
    from lumen.engine.services.hosting.ops_scheduler import start_ops_scheduler
    assert callable(start_ops_scheduler)

def test_projects_api_paths_in_app():
    src = (REPO / "lumen/api/app.py").read_text(encoding="utf-8")
    assert 'add_get("/v1/projects"' in src or "/v1/projects" in src
    assert "/v1/projects/{id}/logs" in src
    assert "/v1/projects/{id}/redeploy" in src
    assert 'add_delete("/v1/projects/{id}"' in src

def test_service_uses_orchestration_start_host():
    src = (REPO / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "orchestration import start_host" in src or "orchestration import start_host as" in src
    assert "ops_scheduler" in src

def test_worker_uses_orchestration():
    src = (REPO / "lumen/engine/services/hosting/worker.py").read_text(encoding="utf-8")
    assert "orchestration" in src

def test_alerter_has_email():
    from lumen.engine.services.hosting import alerter
    assert hasattr(alerter, "_email")
