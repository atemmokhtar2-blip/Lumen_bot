"""Part 2 — hosting components: storage space, runtime manifest, lifecycle restart."""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_project_space_creates_layout(tmp_path: Path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "bot.db").write_bytes(b"sqlite")
    from lumen.hosting.project_space import ensure_project_space, SUBDIRS

    sp = ensure_project_space(tmp_path, user_id=42)
    for d in SUBDIRS:
        assert (tmp_path / d).is_dir()
    assert (tmp_path / "data" / "bot.db").is_file() or (tmp_path / "bot.db").is_file()
    assert (tmp_path / ".lumen_space.json").is_file()
    assert sp.user_id == 42


def test_runtime_manifest_written(tmp_path: Path):
    from lumen.hosting.project_space import write_runtime_manifest, load_runtime_manifest

    write_runtime_manifest(
        tmp_path,
        entry_point="main.py",
        backend="firecracker",
        env_keys=["BOT_TOKEN"],
        details={"version_ref": "abc"},
    )
    m = load_runtime_manifest(tmp_path)
    assert m["entry_point"] == "main.py"
    assert m["backend"] == "firecracker"
    assert m["space"]["data"] == "data/"
    assert "webhook_path_template" in m["ports"]


def test_prepare_creates_space_and_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    (tmp_path / "main.py").write_text("print('bot')\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("\n", encoding="utf-8")
    from lumen.engine.services.hosting.prepare_runtime import prepare_project_for_host

    r = prepare_project_for_host(tmp_path, install_deps=False)
    assert r.ok, r.message
    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / ".lumen_runtime.json").is_file()
    data = json.loads((tmp_path / ".lumen_runtime.json").read_text(encoding="utf-8"))
    assert data["entry_point"] == "main.py"


def test_hosting_service_has_restart():
    from lumen.engine.services.hosting.service import HostingService
    assert callable(getattr(HostingService, "restart", None))


def test_api_has_restart_routes():
    src = (REPO / "lumen/api/app.py").read_text(encoding="utf-8")
    assert "/projects/{id}/restart" in src
    assert "project_restart" in src


def test_network_documents_firecracker():
    from lumen.engine.services.hosting.network import permanent_host_network_notes

    notes = permanent_host_network_notes()
    assert "Firecracker" in notes or "firecracker" in notes.lower()
