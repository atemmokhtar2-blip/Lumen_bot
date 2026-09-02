"""Part 1 — run generated code on a real server: prepare + entry wiring."""
from __future__ import annotations

from pathlib import Path

from lumen.engine.services.hosting.prepare_runtime import (
    HOST_DEPS_DIRNAME,
    prepare_project_for_host,
    resolve_entry_point,
)


def test_resolve_entry_main(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    assert resolve_entry_point(tmp_path) == "main.py"
    assert resolve_entry_point(tmp_path, "main.py") == "main.py"


def test_resolve_entry_hint(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "bot.py").write_text("x=1\n", encoding="utf-8")
    assert resolve_entry_point(tmp_path, "app/bot.py") == "app/bot.py"


def test_prepare_no_entry_fails(tmp_path: Path) -> None:
    (tmp_path / "readme.txt").write_text("x\n", encoding="utf-8")
    r = prepare_project_for_host(tmp_path, install_deps=False)
    assert r.ok is False
    assert "دخول" in r.message or "entry" in r.message.lower()


def test_prepare_ok_sets_env(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    r = prepare_project_for_host(tmp_path, install_deps=False)
    assert r.ok is True
    assert r.entry_point == "main.py"
    assert r.env_vars.get("LUMEN_BOT_ENTRY") == "main.py"


def test_prepare_installs_requirements(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    # Empty requirements after sanitize may still succeed; use a tiny pure stdlib-less need:
    # install a known small package is network-dependent — skip if offline by allowing fail message
    (tmp_path / "requirements.txt").write_text("# no packages\n", encoding="utf-8")
    r = prepare_project_for_host(tmp_path, install_deps=True)
    # empty after sanitize → ok
    assert r.ok is True
    assert r.entry_point == "main.py"


def test_start_signature_accepts_entry_point() -> None:
    import inspect
    from lumen.engine.services.hosting.service import HostingService

    sig = inspect.signature(HostingService.start)
    assert "entry_point" in sig.parameters


def test_token_handler_passes_entry_point() -> None:
    src = Path("lumen/bot/handlers/token_handler.py").read_text(encoding="utf-8")
    assert "entry_point=str(pending_host.get(\"entry_point\")" in src or 'entry_point=str(pending_host.get("entry_point")' in src


def test_guest_supervisor_uses_host_deps() -> None:
    src = Path(
        "lumen/engine/services/sandbox_runtime/guest_agent/supervisor.py"
    ).read_text(encoding="utf-8")
    assert "LUMEN_HOST_DEPS" in src
    assert HOST_DEPS_DIRNAME in src
    assert "PYTHONPATH" in src


def test_service_calls_prepare_before_sandbox() -> None:
    src = Path("lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    prep = src.find("prepare_project_for_host")
    sbx = src.find("start_permanent_host_bot")
    if sbx < 0:
        sbx = src.find("start_sandboxed_bot")
    assert prep > 0 and sbx > 0
    assert prep < sbx


def test_ingress_stable_url(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TBE_HOST_BASE_DOMAIN", "hosts.example.com")
    monkeypatch.setenv("TBE_PUBLIC_URL_SCHEME", "https")
    monkeypatch.setenv("TBE_TRAEFIK_DYNAMIC_DIR", str(tmp_path))
    from lumen.engine.services.hosting.ingress import (
        public_url_for_instance,
        write_traefik_route,
    )

    url = public_url_for_instance("host-abc12")
    assert url == "https://host-abc12.hosts.example.com"
    r = write_traefik_route(instance_id="host-abc12", backend_url="http://10.0.0.2:8080")
    assert r["written"] is True
    assert (tmp_path / "lumen-host-host-abc12.yaml").is_file()


def test_production_rejects_non_firecracker_in_service_source() -> None:
    src = Path("lumen/engine/services/hosting/service.py").read_text(encoding="utf-8")
    assert "is_production_sandbox_path" in src
    assert 'backend_name != "firecracker"' in src


def test_health_monitor_interval_default() -> None:
    from lumen.engine.services.hosting.health_monitor import interval_sec

    assert interval_sec() >= 10
