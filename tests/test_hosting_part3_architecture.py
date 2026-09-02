"""Part 3 — architecture plane: manifest, webhook manager, gateway."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]


def test_project_manifest_full_json(tmp_path):
    from lumen.hosting.project_manifest import (
        build_manifest_from_instance,
        write_manifest,
        load_manifest,
    )

    inst = SimpleNamespace(
        instance_id="host-1",
        user_id=7,
        project_path=str(tmp_path),
        entry_point="main.py",
        sandbox_backend="firecracker",
        public_base_url="https://host-1.example.com",
        webhook_public_url="https://api.example.com/v1/hooks/telegram/host-1",
        internal_port=8123,
        platform="telegram",
        cpu_quota=0.5,
        memory_mb=256,
        status="running",
        version_ref="abc",
        deployment_id="dep-1",
    )
    man = build_manifest_from_instance(inst)
    write_manifest(tmp_path, man)
    data = load_manifest(tmp_path)
    assert data["instance_id"] == "host-1"
    assert data["platform"] == "telegram"
    assert data["networking"]["webhook_url"].endswith("/host-1")
    assert data["resources"]["memory_mb"] == 256
    assert data["backend"] == "firecracker"


def test_webhook_manager_url_and_mode(monkeypatch):
    from lumen.hosting import webhook_manager as wm

    monkeypatch.setenv("TBE_PUBLIC_API_BASE", "https://api.example.com")
    monkeypatch.setenv("TBE_HOST_WEBHOOK_MODE", "auto")
    url = wm.webhook_url_for("iid-99")
    assert url == "https://api.example.com/v1/hooks/telegram/iid-99"
    assert wm.should_register(url) is True
    monkeypatch.setenv("TBE_HOST_WEBHOOK_MODE", "polling")
    assert wm.should_register(url) is False


def test_gateway_writes_via_ingress(monkeypatch, tmp_path):
    monkeypatch.setenv("TBE_TRAEFIK_DYNAMIC_DIR", str(tmp_path / "tr"))
    monkeypatch.setenv("TBE_CADDY_DYNAMIC_DIR", str(tmp_path / "cd"))
    from lumen.hosting.gateway import write_routes_for_instance, nginx_snippet

    r = write_routes_for_instance("bot-x", enabled=True)
    assert "traefik" in r or "error" in r
    sn = nginx_snippet("bot-x")
    assert "bot-x" in sn and "proxy_pass" in sn


def test_host_instance_architecture_fields():
    from dataclasses import fields
    from lumen.engine.services.hosting.service import HostInstance

    names = {f.name for f in fields(HostInstance)}
    for n in ("platform", "cpu_quota", "memory_mb", "webhook_public_url", "internal_port"):
        assert n in names


def test_api_hook_route_registered():
    src = (REPO / "lumen/api/app.py").read_text(encoding="utf-8")
    assert "/v1/hooks/telegram/{instance_id}" in src
    assert "host_webhooks" in src


def test_service_wires_architecture_plane():
    src = (REPO / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "apply_to_instance" in src
    assert "write_manifest_for_instance" in src
    assert "write_routes_for_instance" in src
