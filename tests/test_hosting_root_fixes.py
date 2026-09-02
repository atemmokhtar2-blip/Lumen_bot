"""Root fixes: FC-only permanent host, Redis registry, versions, seccomp, ingress."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_permanent_host_starter_exists_and_is_fc_only() -> None:
    from lumen.engine.services.sandbox_runtime.select import start_permanent_host_bot
    import inspect

    src = inspect.getsource(start_permanent_host_bot)
    assert "FirecrackerSandboxBackend" in src
    assert "backend.start(spec)" in src
    assert "FirecrackerSandboxBackend()" in src
    assert "Docker" not in src or "not accepted" in src.lower() or "Never Docker" in src


def test_hosting_service_uses_permanent_starter() -> None:
    src = (REPO / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "start_host" in src or "orchestration" in src
    assert "start_sandboxed_bot(" not in src


def test_redis_state_module_api() -> None:
    from lumen.engine.services.hosting import redis_state as rs

    assert callable(rs.put_instance)
    assert callable(rs.get_instance)
    assert callable(rs.delete_instance)


def test_versions_publish_list_restore(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    from lumen.engine.services.hosting.versions import (
        list_versions,
        publish_version,
        restore_version,
    )

    entry = publish_version(tmp_path, "deadbeefcafebabe")
    assert entry["version_ref"] == "deadbeefcafebabe"
    assert entry.get("artifact_uri")
    vers = list_versions(tmp_path)
    assert any(v["version_ref"] == "deadbeefcafebabe" for v in vers)
    # mutate then restore
    (tmp_path / "main.py").write_text("print(2)\n", encoding="utf-8")
    restore_version(tmp_path, "deadbeefcafebabe")
    assert "print(1)" in (tmp_path / "main.py").read_text(encoding="utf-8")


def test_docker_seccomp_fail_closed_in_source() -> None:
    src = (REPO / "lumen/engine/services/sandbox_runtime/docker_backend.py").read_text(
        encoding="utf-8"
    )
    assert "docker_seccomp_required" in src
    assert "TBE_DOCKER_ALLOW_NO_SECCOMP" in src


def test_ingress_traefik_and_caddy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TBE_HOST_BASE_DOMAIN", "bots.example.com")
    monkeypatch.setenv("TBE_TRAEFIK_DYNAMIC_DIR", str(tmp_path / "t"))
    monkeypatch.setenv("TBE_CADDY_DYNAMIC_DIR", str(tmp_path / "c"))
    from lumen.engine.services.hosting.ingress import (
        public_url_for_instance,
        write_caddy_route,
        write_traefik_route,
    )

    assert public_url_for_instance("host-xyz") == "https://host-xyz.bots.example.com"
    assert write_traefik_route(instance_id="host-xyz")["written"] is True
    assert write_caddy_route(instance_id="host-xyz")["written"] is True


def test_host_instance_has_public_and_version_fields() -> None:
    from dataclasses import fields
    from lumen.engine.services.hosting.service import HostInstance

    names = {f.name for f in fields(HostInstance)}
    assert "public_base_url" in names
    assert "version_ref" in names
    assert "last_health_at" in names


def test_worker_uses_permanent_host_bot_not_generic() -> None:
    src = (REPO / "lumen/engine/services/hosting/worker.py").read_text(encoding="utf-8")
    assert "orchestration" in src or "start_host" in src
    assert "start_sandboxed_bot" not in src


def test_service_stop_and_alive_no_docker() -> None:
    src = (REPO / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "DockerProcessDriver" not in src
    assert "docker inspect" not in src
    assert "orchestration" in src or "start_host" in src


def test_service_get_and_list_use_redis() -> None:
    src = (REPO / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "host_redis.get_instance" in src
    assert "host_redis.list_for_user" in src


def test_set_telegram_webhook_helper_exists() -> None:
    from lumen.bot.singleton import set_telegram_webhook, clear_telegram_webhook

    assert callable(set_telegram_webhook)
    assert callable(clear_telegram_webhook)


def test_host_webhook_route_module() -> None:
    src = (REPO / "lumen/api/routes/host_webhooks.py").read_text(encoding="utf-8")
    assert "telegram_host_webhook" in src
    assert "lumen:host:tgq:" in src


def test_app_registers_host_webhook_and_versions() -> None:
    src = (REPO / "lumen/api/app.py").read_text(encoding="utf-8")
    assert "/v1/hooks/telegram/{instance_id}" in src
    assert "host_list_versions" in src
    assert "host_restore_version" in src


def test_service_webhook_mode_gate_in_source() -> None:
    src = (REPO / "lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "TBE_HOST_WEBHOOK_MODE" in src
    assert "set_telegram_webhook" in src


def test_worker_durable_upsert() -> None:
    src = (REPO / "lumen/engine/services/hosting/worker.py").read_text(encoding="utf-8")
    assert "get_host_state_store" in src
    assert "store.upsert" in src
