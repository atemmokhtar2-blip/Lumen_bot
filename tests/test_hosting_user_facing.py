"""User-facing bindings: host panel, dash effects, notify_user, UI catalog."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]


def test_host_panel_buttons_include_backup_versions():
    from lumen.bot.ui.host_panel import host_panel_buttons

    rows = host_panel_buttons(instance_index="0")
    ids = {b.action for row in rows for b in row}
    assert "dash_logs" in ids
    assert "dash_backup" in ids
    assert "dash_versions" in ids
    assert "dash_stop" in ids


def test_format_host_success_shows_public_and_version():
    from lumen.bot.ui.host_panel import format_host_success

    inst = SimpleNamespace(
        status="running",
        bot_username="mybot",
        instance_id="host-abc123456",
        sandbox_backend="firecracker",
        public_base_url="https://host-abc.example.com",
        version_ref="deadbeefcafebabe",
        project_path="/tmp/proj",
    )
    result = SimpleNamespace(instance=inst, message="ok")
    text = format_host_success(result)
    assert "firecracker" in text or "العزل" in text
    assert "host-abc.example.com" in text or "الرابط" in text
    assert "deadbeef" in text or "الإصدار" in text
    assert "AES" in text or "مشفّر" in text


def test_ui_catalog_knows_backup_versions():
    from lumen.engine.services.ui_state.catalog import is_known_action

    assert is_known_action("dash_backup")
    assert is_known_action("dash_versions")


def test_controller_sets_dash_effect_backup():
    from lumen.engine.services.ui_state.controller import apply_action
    from lumen.engine.services.ui_state.models import EngineUiPhase, EngineUiState
    import inspect

    st = EngineUiState(phase=EngineUiPhase.DASHBOARD)
    sig = inspect.signature(apply_action)
    kwargs = {}
    params = list(sig.parameters)
    # flexible call
    try:
        res = apply_action(st, "dash_backup", "0")
    except TypeError:
        try:
            res = apply_action(state=st, action_id="dash_backup", arg="0")
        except TypeError:
            res = apply_action(st, action_id="dash_backup", arg="0", user_id=1)
    assert getattr(res, "ok", False)
    assert getattr(res, "dash_effect", "") == "dash_backup"


def test_notify_user_callable():
    from lumen.hosting.alerter import notify_user, alert_instance_failed

    assert callable(notify_user)
    # no token → False without crash
    assert notify_user(0, "x") is False
    r = alert_instance_failed(instance_id="i", user_id=1, reason="down")
    assert "user" in r or "telegram" in r


def test_dash_actions_source_wires_hosting_ops():
    src = (REPO / "lumen/bot/ui/dash_actions.py").read_text(encoding="utf-8")
    assert "dash_backup" in src
    assert "backup_project" in src
    assert "list_versions" in src
    assert "dash_versions" in src
