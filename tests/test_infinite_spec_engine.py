"""Unit tests for infinite atomic-spec engine."""
from __future__ import annotations

import pytest


SAMPLE = {
    "bot_name": "support_bot",
    "language": "ar",
    "description": "simple support",
    "version": "infinite_v1",
    "nodes": [
        {
            "id": "start_node",
            "trigger": {"type": "on_start", "config": {}},
            "conditions": [{"type": "always", "config": {}}],
            "actions": [
                {"type": "send_message", "config": {"text": "مرحباً — كيف أساعدك؟"}}
            ],
            "next_node_id": None,
        },
        {
            "id": "help_node",
            "trigger": {"type": "on_command", "config": {"command": "help"}},
            "actions": [
                {"type": "send_message", "config": {"text": "الأوامر: /start /help"}}
            ],
        },
    ],
}


def test_validate_ok():
    from telegram_bot_engine.spec_core.infinite import validate_dynamic_spec

    dyn = validate_dynamic_spec(SAMPLE)
    assert dyn.bot_name == "support_bot"
    assert len(dyn.nodes) == 2


def test_reject_unknown_action():
    from telegram_bot_engine.spec_core.infinite import validate_dynamic_spec, SpecValidationError

    bad = {
        **SAMPLE,
        "nodes": [
            {
                "id": "x",
                "trigger": {"type": "on_start", "config": {}},
                "actions": [{"type": "exec_shell", "config": {}}],
            }
        ],
    }
    with pytest.raises(Exception):
        validate_dynamic_spec(bad)


def test_reject_cycle():
    from telegram_bot_engine.spec_core.infinite.ast_validator import validate_dynamic_spec, SpecValidationError

    cyc = {
        "bot_name": "loop",
        "nodes": [
            {
                "id": "a",
                "trigger": {"type": "on_message", "config": {}},
                "actions": [{"type": "noop", "config": {}}],
                "next_node_id": "b",
            },
            {
                "id": "b",
                "trigger": {"type": "on_message", "config": {}},
                "actions": [{"type": "noop", "config": {}}],
                "next_node_id": "a",
            },
        ],
    }
    with pytest.raises(SpecValidationError) as ei:
        validate_dynamic_spec(cyc)
    assert ei.value.code == "infinite_loop_detected"


def test_reject_ssrf_api():
    from telegram_bot_engine.spec_core.infinite.ast_validator import validate_dynamic_spec, SpecValidationError

    bad = {
        "bot_name": "x",
        "nodes": [
            {
                "id": "a",
                "trigger": {"type": "on_command", "config": {"command": "x"}},
                "actions": [
                    {"type": "call_external_api", "config": {"url": "http://127.0.0.1/admin"}}
                ],
            }
        ],
    }
    with pytest.raises(SpecValidationError):
        validate_dynamic_spec(bad)


def test_compile_to_botspec():
    from telegram_bot_engine.spec_core.infinite import compile_dynamic_spec

    bot = compile_dynamic_spec(SAMPLE)
    assert bot.bot.name == "support_bot"
    assert len(bot.features) >= 2
    assert "engine:infinite_v1" in bot.hard_constraints


def test_render_handlers_runs():
    from telegram_bot_engine.spec_core.infinite import render_handlers_python, validate_dynamic_spec

    code = render_handlers_python(SAMPLE)
    assert "def run_flow" in code
    ns: dict = {}
    exec(code, ns)
    out = ns["run_flow"]({"type": "on_command", "command": "help", "text": ""}, {})
    assert out and out[0]["action"]["type"] == "send_message"


def test_macro_promote(tmp_path, monkeypatch):
    monkeypatch.setenv("TBE_MACRO_REGISTRY_DIR", str(tmp_path))
    from telegram_bot_engine.spec_core.infinite.macro_registry import MacroRegistry

    reg = MacroRegistry(root=tmp_path)
    mid = reg.promote(SAMPLE, macro_id="support_v1")
    assert mid == "support_v1"
    loaded = reg.get("support_v1")
    assert loaded is not None
    assert len(reg.list_macros()) >= 1


def test_compose_from_json_string():
    import json
    from telegram_bot_engine.spec_core.infinite.compose import compose_infinite_from_payload

    bot, dyn = compose_infinite_from_payload(json.dumps(SAMPLE))
    assert dyn.bot_name == "support_bot"
    assert bot.features


def test_action_aliases_update_db_call_api():
    from telegram_bot_engine.spec_core.infinite import validate_dynamic_spec, route_and_execute

    spec = {
        "bot_name": "alias_bot",
        "nodes": [
            {
                "id": "n1",
                "trigger": {"type": "on_command", "config": {"command": "set"}},
                "conditions": [{"type": "state_check", "config": {"key": "x", "value": 1}}],
                "actions": [
                    {"type": "update_db", "config": {"key": "x", "value": 2}},
                    {"type": "change_state", "config": {"key": "y", "value": 3}},
                ],
            }
        ],
    }
    dyn = validate_dynamic_spec(spec)
    assert dyn.nodes[0].actions[0].type == "update_state"
    out = route_and_execute(
        dyn,
        {"type": "on_command", "command": "set", "text": ""},
        state={"x": 1},
        mode="interpreter",
    )
    assert out["ok"]
    assert out["state"].get("x") == 2


def test_schema_py_reexports():
    from telegram_bot_engine.spec_core.schema import DynamicBotSpec, FlowNode, validate_dynamic_spec
    assert DynamicBotSpec is not None
    assert FlowNode is not None
    assert validate_dynamic_spec is not None


def test_ssrf_proxy():
    from telegram_bot_engine.spec_core.infinite.api_proxy import validate_egress_url
    import pytest
    with pytest.raises(ValueError):
        validate_egress_url("http://127.0.0.1/")
    with pytest.raises(ValueError):
        validate_egress_url("https://169.254.169.254/latest")
